"""Ollama / OpenAI-compatible LLM client for clinical variant analysis.

Reads connection settings from the app_settings table (managed via Admin page).
Supports both the native Ollama API (/api/chat) and OpenAI-compatible endpoints
(/v1/chat/completions) — detected automatically by the base URL.
"""

import json
import logging

import requests

from app import admin as admin_module

log = logging.getLogger(__name__)

_TIMEOUT = 120  # seconds — LLM inference can be slow


def _get_client_settings():
    s = admin_module.get_ollama_settings()
    base_url = (s.get("base_url") or "").rstrip("/")
    model = (s.get("model") or "llama3").strip()
    api_key = (s.get("api_key") or "").strip()
    return base_url, model, api_key


def is_configured():
    base_url, _, _ = _get_client_settings()
    return bool(base_url)


def _chat(messages, base_url, model, api_key):
    """Send a chat request and return the assistant reply as a string."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Use OpenAI-compatible endpoint when /v1 is in the path or the URL looks
    # like a hosted service; fall back to native Ollama /api/chat otherwise.
    if "/v1" in base_url or "openai" in base_url or "api.ollama" in base_url:
        url = f"{base_url}/chat/completions"
        payload = {"model": model, "messages": messages, "stream": False}
        resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    else:
        url = f"{base_url}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        resp = requests.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


_ANALYZE_SYSTEM = """\
You are an expert clinical geneticist specializing in rare and undiagnosed diseases.
You will receive a patient's clinical description (including family history if available)
and a list of genetic variants with annotation data from VCF INFO fields.

For each variant, perform the following analysis and return a structured JSON response.
Return ONLY a valid JSON array — no markdown, no text outside the array.

== Analysis tasks ==
1. Reason through five clinical points (see fields below).
2. Recommend ACMG/AMP 2015 criteria that are SUPPORTED by available data.
   Pathogenic evidence: PVS1, PS1, PS2, PS3, PS4, PM1, PM2, PM3, PM4, PM5, PM6, PP1, PP2, PP3, PP4, PP5
   Benign evidence: BA1, BS1, BS2, BS3, BS4, BP1, BP2, BP3, BP4, BP5, BP6, BP7
3. Identify criteria that CANNOT be evaluated due to missing annotation data,
   and state exactly what data is needed.
   Common missing items: population allele frequency (PM2/BA1/BS1), in-silico scores
   like CADD/SIFT/PolyPhen (PP3/BP4), de novo status (PS2/PM6), segregation data (PP1/BS4),
   functional studies (PS3/BS3), phasing information (PM3/BP2), ClinVar evidence (PS1/PP5/BP6).

== Output format ==
[
  {
    "id": <variant_id_integer>,
    "patient_symptoms": "<2-3 sentences: what phenotypes/symptoms does this patient have?>",
    "gene_diseases": "<2-3 sentences: what known diseases are associated with this gene?>",
    "relevance": "<2-3 sentences: does the gene/variant match the patient phenotype?>",
    "family_history": "<1-2 sentences: how does the family history affect interpretation?>",
    "score_rationale": "<1-2 sentences: overall pathogenicity likelihood>",
    "suggested_acmg": ["<code>", ...],
    "missing_data": [
      "<CriterionCode>: <what specific data is missing and why it matters>"
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
                "family_history": item.get("family_history", ""),
                "score_rationale": item.get("score_rationale", ""),
                "suggested_acmg": item.get("suggested_acmg", []),
                "missing_data": item.get("missing_data", []),
            }
        return out
    except Exception as exc:
        log.warning("LLM variant analysis failed: %s", exc)
        return {"error": str(exc)}
