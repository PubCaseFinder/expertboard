"""Ollama / OpenAI-compatible LLM client for clinical variant analysis.

Reads connection settings from the app_settings table (managed via Admin page).
Supports both the native Ollama API (/api/chat) and OpenAI-compatible endpoints
(/v1/chat/completions) — detected automatically by the base URL.
"""

import json
import logging
from urllib.parse import urlparse

import requests

from app import admin as admin_module

log = logging.getLogger(__name__)

_TIMEOUT = 900  # seconds — LLM inference can be slow if running at higher context sizes


def _normalize_base_url(raw_url):
    """Accept host/base URLs and trim common endpoint suffixes.

    Users often paste full endpoints (e.g. /api/chat or /v1/chat/completions).
    Internally we keep only the base so _chat can append the correct path.
    """
    base_url = (raw_url or "").strip().rstrip("/")
    if base_url.endswith("/api/chat"):
        return base_url[: -len("/api/chat")]
    if base_url.endswith("/api"):
        return base_url
    if base_url.endswith("/v1/chat/completions"):
        return base_url[: -len("/chat/completions")]
    if base_url.endswith("/chat/completions") and "/v1" in base_url:
        return base_url[: -len("/chat/completions")]
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


def is_configured():
    base_url, _, _ = _get_client_settings()
    return bool(base_url)


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
            return resp.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 403 and _is_ollama_cloud(base_url):
                raise RuntimeError(
                    "Ollama Cloud returned 403 Forbidden. Check that the API key is valid, "
                    "the model name is available to your account, and the base URL is https://ollama.com/api."
                ) from exc
            raise
    else:
        if base_url.endswith("/api"):
            url = f"{base_url}/chat"
        else:
            url = f"{base_url}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 403 and _is_ollama_cloud(base_url):
                raise RuntimeError(
                    "Ollama Cloud returned 403 Forbidden. Check that the API key is valid, "
                    "the model name is available to your account, and the base URL is https://ollama.com/api."
                ) from exc
            raise


_ANALYZE_SYSTEM = """\
You are an expert clinical geneticist specializing in rare and undiagnosed diseases.

You will receive:
- a patient's clinical description (including family history if available)
- a list of genetic variants with annotation data from VCF INFO fields (including VEP annotations)

For each variant, perform the following analysis and return a structured JSON response.

Return ONLY a valid JSON array. Do not include markdown or any explanatory text.

== Interpretation guidelines ==

Interpret variants according to:
- ACMG/AMP 2015 variant interpretation guidelines

- PM2 should be applied as PM2_Supporting (not PM2), following the ClinGen SVI recommendation on rarity/absence from population databases.

Do not invent evidence. Only recommend criteria that are directly supported by the available data.

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

- PS1 / PP5 / BP6:
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
    "missing_data": [
      "<Criterion>: <required data>"
    ],
    "score": <integer 0-10>
  }
]
"""


def analyze_variants(clinical_text, variants):
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

    variant_list = []
    for v in variants:
        variant_list.append({
            "id": v.id,
            "gene": v.gene or "",
            "hgvs_c": v.hgvs_c or "",
            "hgvs_p": v.hgvs_p or "",
            "variant_type": v.variant_type or "",
            "clin_sig": v.clin_sig or "",
            "genotype": v.genotype or "",
            "depth": v.depth,
            "raw_info": v.raw_info or "",
        })

    user_message = (
        f"Patient clinical description:\n{clinical_text or '(not provided)'}\n\n"
        f"Variants to analyze:\n{json.dumps(variant_list, ensure_ascii=False)}"
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
                "missing_data": item.get("missing_data", []),
            }
        return out
    except Exception as exc:
        log.warning("LLM variant analysis failed: %s", exc)
        return {"error": str(exc)}
