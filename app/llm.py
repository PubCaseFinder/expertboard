"""Ollama / OpenAI-compatible LLM client for clinical variant analysis.

Reads connection settings from the app_settings table (managed via Admin page).
Supports both the native Ollama API (/api/chat) and OpenAI-compatible endpoints
(/v1/chat/completions) — detected automatically by the base URL.
"""

import json
import logging
import re
from urllib.parse import urlparse

import requests

from app import admin as admin_module
from app import hpo_client
from app import vep_api

log = logging.getLogger(__name__)

_TIMEOUT = 900  # seconds — LLM inference can be slow if running at higher context sizes
_HPO_EXTRACTION_CHUNK_SIZE = 1000


def _vcf_info_values(raw_info):
    """Parse persisted VCF INFO values needed for structured LLM context."""
    values = {}
    for item in (raw_info or "").split(";"):
        key, separator, value = item.partition("=")
        if separator and value not in ("", "."):
            values[key] = value
    return values


def _normalize_base_url(raw_url):
    """Accept host/base URLs and trim common endpoint suffixes.

    Users often paste full endpoints (e.g. /api/chat or /v1/chat/completions).
    Internally we keep only the base so _chat can append the correct path.
    """
    base_url = (raw_url or "").strip().rstrip("/")
    if base_url.endswith("/api/chat"):
        base_url = base_url[: -len("/api/chat")]
    elif base_url.endswith("/v1/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    elif base_url.endswith("/chat/completions") and "/v1" in base_url:
        base_url = base_url[: -len("/chat/completions")]

    parsed = urlparse(base_url)
    if parsed.netloc.lower().endswith("ollama.com"):
        # Ollama Cloud only serves HTTPS on the /api path; plain http:// hangs until timeout.
        path = parsed.path if parsed.path not in ("", "/") else "/api"
        base_url = f"https://{parsed.netloc}{path}".rstrip("/")
    return base_url


def _get_client_settings():
    s = admin_module.get_ollama_settings()
    base_url = _normalize_base_url(s.get("base_url"))
    model = (s.get("model") or "llama3").strip()
    api_key = (s.get("api_key") or "").strip()
    return base_url, model, api_key


def _is_ollama_cloud(base_url):
    try:
        return urlparse(base_url).netloc.lower().endswith("ollama.com")
    except Exception:
        return False


def _format_http_error(url, model, response):
    """Return an actionable LLM error without exposing request credentials."""
    detail = (response.text or "").strip().replace("\n", " ")
    if len(detail) > 500:
        detail = detail[:500] + "..."
    return (
        f"LLM request failed with HTTP {response.status_code} for model '{model}'. "
        f"Server response: {detail or 'No response body.'} "
        f"Check the model name and endpoint settings."
    )


def is_configured():
    base_url, _, _ = _get_client_settings()
    return bool(base_url)


_HPO_EXTRACTION_SYSTEM = """\
You are a clinical phenotyping assistant. Extract only phenotypes explicitly
present in the supplied clinical text. A terminology service will map the
extracted labels to Human Phenotype Ontology (HPO) identifiers.

Return ONLY one valid JSON object with this shape:
{
  "phenotypes": [
    {
    "label": "concise clinical phenotype",
      "source_text": "short exact phrase from the clinical text"
    }
  ]
}

Rules:
- Include only patient findings, not diagnoses, genes, tests, treatments, or family-member findings.
- Exclude negated findings, ruled-out findings, and hypothetical findings.
- Extract each explicitly stated symptom, examination finding, developmental finding, or abnormal measurement.
- Do not decide or return HPO identifiers; return phenotype labels even when you do not know an HPO identifier.
- Use a concise phenotype label suitable for terminology lookup.
- Preserve the meaning of onset, severity, laterality, and frequency when choosing a term.
- Deduplicate synonymous findings.
- Return an empty phenotypes array only when the text contains no explicit patient phenotype.
"""

_CLINICAL_CONTEXT_EXTRACTION_SYSTEM = """\
Extract only an explicitly stated patient ancestry, ethnicity, country of origin,
or diagnosis/disease from the supplied clinical note. Do not infer ancestry from
a name, language, location of care, or diagnosis. Return ONLY valid JSON:
{"ancestry": [{"value": "...", "source_text": "exact phrase"}],
 "diseases": [{"value": "...", "source_text": "exact phrase"}]}
Use empty arrays when the note does not explicitly state a value.
"""


def extract_hpo_phenotypes(clinical_text):
    """Use the configured LLM to extract HPO candidates from clinical text."""
    if not (clinical_text or "").strip():
        return []
    base_url, model, api_key = _get_client_settings()
    if not base_url:
        raise RuntimeError("Ollama is not configured. Set the URL in Admin.")

    candidates = []
    text = clinical_text.strip()
    for start in range(0, len(text), _HPO_EXTRACTION_CHUNK_SIZE):
        chunk = text[start:start + _HPO_EXTRACTION_CHUNK_SIZE]
        raw = _chat(
            [
                {"role": "system", "content": _HPO_EXTRACTION_SYSTEM},
                {"role": "user", "content": chunk},
            ],
            base_url,
            model,
            api_key,
        ).strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON for HPO extraction.") from exc
        for item in payload.get("phenotypes", []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            candidates.append(
                {
                    "label": label,
                    "source_text": str(item.get("source_text") or ""),
                }
            )

    unique_candidates = []
    seen_labels = set()
    for candidate in candidates:
        normalized = candidate["label"].casefold()
        if normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        unique_candidates.append(candidate)
    return unique_candidates


def extract_clinical_context(clinical_text):
    """Extract reviewable ancestry and disease candidates from a clinical note."""
    if not (clinical_text or "").strip():
        return {"ancestry": [], "diseases": []}
    base_url, model, api_key = _get_client_settings()
    if not base_url:
        raise RuntimeError("Ollama is not configured. Set the URL in Admin.")
    raw = _chat(
        [{"role": "system", "content": _CLINICAL_CONTEXT_EXTRACTION_SYSTEM},
         {"role": "user", "content": clinical_text.strip()}],
        base_url, model, api_key,
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].removeprefix("json")
    try:
        context = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON for clinical context extraction.") from exc
    return {
        key: [item for item in context.get(key, []) if isinstance(item, dict)]
        for key in ("ancestry", "diseases")
    }


def _chat(messages, base_url, model, api_key):
    """Send a chat request and return the assistant reply as a string."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif _is_ollama_cloud(base_url):
        raise RuntimeError(
            "Ollama Cloud requires an API key. Add it in Admin → LLM settings and retry."
        )

    # Use OpenAI-compatible endpoint when /v1 is in the path or the URL looks
    # like a hosted service; fall back to native Ollama /api/chat otherwise.
    if "/v1" in base_url or "openai" in base_url or "api.ollama" in base_url:
        url = f"{base_url}/chat/completions"
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            try:
                return resp.json()["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                log.error(
                    f"Failed to parse OpenAI-compatible response from {url}. "
                    f"Status: {resp.status_code}. Response: {resp.text[:500]}"
                )
                raise RuntimeError(
                    f"Invalid response from LLM server at {url}: {type(exc).__name__}. "
                    f"Server may not be running or endpoint may be incorrect. "
                    f"Response started with: {resp.text[:100]}"
                ) from exc
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 403 and _is_ollama_cloud(base_url):
                raise RuntimeError(
                    "Ollama Cloud returned 403 Forbidden. Check that the API key is valid, "
                    "the model name is available to your account, and the base URL is https://ollama.com/api."
                ) from exc
            log.error(
                f"HTTP error from {url}: {status}. Response: {exc.response.text[:500]}"
            )
            raise RuntimeError(_format_http_error(url, model, exc.response)) from exc
    else:
        if base_url.endswith("/api"):
            url = f"{base_url}/chat"
        else:
            url = f"{base_url}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            try:
                return resp.json()["message"]["content"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.error(
                    f"Failed to parse Ollama response from {url}. "
                    f"Status: {resp.status_code}. Response: {resp.text[:500]}"
                )
                raise RuntimeError(
                    f"Invalid response from LLM server at {url}: {type(exc).__name__}. "
                    f"Server may not be running or endpoint may be incorrect. "
                    f"Response started with: {resp.text[:100]}"
                ) from exc
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 403 and _is_ollama_cloud(base_url):
                raise RuntimeError(
                    "Ollama Cloud returned 403 Forbidden. Check that the API key is valid, "
                    "the model name is available to your account, and the base URL is https://ollama.com/api."
                ) from exc
            log.error(
                f"HTTP error from {url}: {status}. Response: {exc.response.text[:500]}"
            )
            raise RuntimeError(_format_http_error(url, model, exc.response)) from exc


_ANALYZE_SYSTEM = """\
You are an expert clinical geneticist specializing in rare and undiagnosed diseases.

You will receive:
- a patient's clinical description (including family history if available)
- a list of genetic variants with annotation data from VCF INFO fields (including VEP annotations)
- when available, a latest_external_annotation object containing live VEP and VRS results
- when available, case_external_evidence containing PubCaseFinder phenotype rankings and case reports

For each variant, perform the following analysis and return a structured JSON response.

Return ONLY a valid JSON array. Do not include markdown or any explanatory text.

== Interpretation guidelines ==

Interpret variants according to:
- ACMG/AMP 2015 variant interpretation guidelines

- PM2 should be applied as PM2_Supporting (not PM2), following the ClinGen SVI recommendation on rarity/absence from population databases.

Do not invent evidence. Only recommend criteria that are directly supported by the available data.
Prefer latest_external_annotation over older VCF INFO values when they conflict.
For population frequency, first use the explicit vcf_population_frequency field when provided.
It is the imported gnomAD annotation and is valid even if live VEP omits frequency data.
Use a population-specific gnomAD AF only when the patient's clinical description explicitly
states a matching country, ethnicity, ancestry, or population. Do not infer ancestry from a
name, diagnosis, language, or location of care. If no explicit match is available, use
gnomAD_AF_ALL. If gnomAD_AF_ALL is available, do not report population frequency as NotProvided.
Use the VRS identifier to establish variant identity only; it is not pathogenicity evidence.
Treat PubCaseFinder rankings as diagnostic-support signals, not proof of causality.
A case-report citation alone does not establish PS3, PS4, or any other ACMG criterion;
apply a criterion only when the supplied evidence contains the required study details.
For every suggested criterion, provide evidence_basis entries naming the exact source field,
observed value, criterion, and a short explanation of how the value supports the suggestion.
If a criterion has no direct supporting value, do not include it in suggested_acmg.

== Analysis tasks ==

For each variant:

1. Summarize the patient's phenotype.
2. Summarize diseases associated with the affected gene.
3. Assess whether the variant is relevant to the patient's phenotype.
4. Assess consistency with the reported family history.
5. Explain the overall prioritization score.

Then:

6. Recommend ACMG/ClinGen evidence codes supported by the available evidence.

In particular, for the following criteria:

| Evidence type                                             | Pathogenic criteria | Benign criteria |
| --------------------------------------------------------- | ------------------- | --------------- |
| **Control population frequency**                          | PM2_Supporting      | BA1, BS1        |
| **Functional evidence**                                   | PS3                 | BS3             |
| **Case / phenotype evidence**                             | PS4, PP4            | —               |
| **Variant-level / same-residue evidence**                 | PS1, PM5            | —               |
| **Variant consequence / molecular mechanism**             | PVS1, PM4           | BP3, BP7        |
| **Computational / predictive evidence**                   | PP3                 | BP4             |
| **Gene / disease mechanism evidence**                     | PM1, PP2            | BP1             |
| **Phenotype / gene relationship or clinical observation** | PP4                 | —               |

7. Identify criteria that cannot be evaluated because required evidence is missing.

Do NOT list criteria that are simply not met.

For each missing criterion, specify exactly what additional data would be required.

Common examples:

- PP3 / BP4:
  Computational evidence (e.g. REVEL, CADD, AlphaMissense, SpliceAI, SIFT, PolyPhen-2).

- PS2 / PM6:
  Confirmed de novo status with parental testing.

- PP1 / BS4:
  Segregation data from affected and unaffected relatives (requires pedigree).

- PS3 / BS3:
  Well-established functional assay results.

- PM3 / BP2:
  Phase information (cis/trans) and genotype of the second allele.

- PS1:
  Expert-reviewed clinical classification (e.g. ClinVar with review status or ClinGen Variant Curation Expert Panel).

== Output format ==
[
  {
    "id": <variant_id_integer>,
    "patient_symptoms": "<2-3 sentences>",
    "gene_diseases": "<2-3 sentences>",
    "relevance": "<2-3 sentences>",
    "population_frequency" : "<gnomAD_AF value">,
    "in_silico_predictions" : "<REVEL, CADD, SpliceAI scores from VCF>",
    "family_history": "<1-2 sentences>",
    "score_rationale": "<1-2 sentences>",
    "suggested_acmg": [
      "<criterion>",
      "<criterion>"
    ],
        "evidence_basis": [
            {
                "criterion": "<criterion>",
                "source": "<VCF INFO, live VEP, PubCaseFinder, or clinical note>",
                "field": "<exact field name>",
                "value": "<observed value>",
                "explanation": "<why this supports the criterion>"
            }
        ],
    "missing_data": [
      "<Criterion>: <required data>"
    ],
    "score": <integer 0-10>
  }
]
"""


def analyze_variants(
    clinical_text,
    variants,
    annotations_by_variant=None,
    case_evidence=None,
    clinical_context=None,
    compact_input=False,
):
    """Analyze variants against clinical text using the configured Ollama model.

    Parameters
    ----------
    clinical_text : str
        Free-text clinical description of the patient.
    variants : list[Variant]
        SQLAlchemy Variant objects to evaluate.

    Returns
    -------
    dict[int, dict]
        Mapping variant_id -> {"score": int, "reason": str}
        Returns an empty dict if LLM is not configured or call fails.
    """
    base_url, model, api_key = _get_client_settings()
    if not base_url:
        return {}

    annotations_by_variant = annotations_by_variant or {}
    variant_list = []
    for v in variants:
        info_values = _vcf_info_values(v.raw_info)
        variant_data = {
            "id": v.id,
            "gene": v.gene or "",
            "hgvs_c": v.hgvs_c or "",
            "hgvs_p": v.hgvs_p or "",
            "variant_type": v.variant_type or "",
            "clin_sig": v.clin_sig or "",
            "genotype": v.genotype or "",
            "depth": v.depth,
            "raw_info": v.raw_info or "",
        }
        population_frequency = {}
        if "gnomAD_AF" in info_values:
            population_frequency["gnomAD_AF_ALL"] = info_values["gnomAD_AF"]
        if "gnomAD_AF_POPMAX" in info_values:
            population_frequency["gnomAD_AF_POPMAX"] = info_values["gnomAD_AF_POPMAX"]
        for key, value in info_values.items():
            if key.startswith("gnomAD_AF_") and key not in population_frequency:
                population_frequency[key] = value
        if population_frequency:
            variant_data["vcf_population_frequency"] = population_frequency
        annotation = annotations_by_variant.get(v.id) or annotations_by_variant.get(
            str(v.id)
        )
        if annotation:
            variant_data["latest_external_annotation"] = annotation
        if compact_input:
            variant_data.pop("raw_info", None)
            variant_data["vcf_info"] = {
                key: value for key, value in info_values.items()
                if key in {
                    "CLNSIG", "REVIEW_STAR", "CLNREVSTAT", "MANE_HIT",
                    "VEP_IMPACT", "VEP_HGVSC", "VEP_HGVSP", "GNOMAD_AF",
                    "gnomAD_AF_POPMAX", "GNOMAD_AF_GRPMAX", "GNOMAD_AF_EAS",
                    "GNOMAD_AF_SAS", "REVEL", "CADD", "CADD_PHRED",
                    "SpliceAI_AG", "SpliceAI_AL", "SpliceAI_DG", "SpliceAI_DL",
                    "AlphaMissense", "AF",
                }
            }
            if annotation:
                variant_data["latest_external_annotation"] = vep_api.compact_annotation_for_llm(annotation)
        variant_list.append(variant_data)

    user_message = (
        f"Patient clinical description:\n{clinical_text or '(not provided)'}\n\n"
        f"Variants to analyze:\n{json.dumps(variant_list, ensure_ascii=False)}"
    )
    if case_evidence:
        user_message += (
            "\n\nCase external evidence:\n"
            + json.dumps(case_evidence, ensure_ascii=False)
        )
    if clinical_context:
        user_message += (
            "\n\nReviewer-confirmed clinical context (use for population selection):\n"
            + json.dumps(clinical_context, ensure_ascii=False)
        )

    messages = [
        {"role": "system", "content": _ANALYZE_SYSTEM},
        {"role": "user", "content": user_message},
    ]

    try:
        raw = _chat(messages, base_url, model, api_key)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        results = json.loads(raw)
        out = {}
        for item in results:
            if "id" not in item:
                continue
            out[item["id"]] = {
                "score": item.get("score", 0),
                "patient_symptoms": item.get("patient_symptoms", ""),
                "gene_diseases": item.get("gene_diseases", ""),
                "relevance": item.get("relevance", ""),
                "population_frequency": item.get("population_frequency", ""),
                "in_silico_predictions": item.get("in_silico_predictions", ""),
                "family_history": item.get("family_history", ""),
                "score_rationale": item.get("score_rationale", ""),
                "suggested_acmg": item.get("suggested_acmg", []),
                "evidence_basis": item.get("evidence_basis", []),
                "missing_data": item.get("missing_data", []),
            }
        return out
    except Exception as exc:
        log.warning("LLM variant analysis failed: %s", exc)
        return {"error": str(exc)}
