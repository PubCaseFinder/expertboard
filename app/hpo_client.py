"""Human Phenotype Ontology term resolution through EMBL-EBI OLS4."""

import re

import requests


OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


def _search(label, exact):
    response = requests.get(
        OLS_SEARCH_URL,
        params={
            "q": label,
            "ontology": "hp",
            "exact": "true" if exact else "false",
            "rows": 5,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("response", {}).get("docs", [])


def resolve_label(label):
    """Return the best current HPO term for a phenotype label."""
    query = str(label or "").strip()
    if not query:
        return None
    for exact in (True, False):
        for document in _search(query, exact):
            hpo_id = str(document.get("obo_id") or "").upper()
            if re.fullmatch(r"HP:\d{7}", hpo_id) and not document.get("is_obsolete"):
                return {
                    "hpo_id": hpo_id,
                    "label": str(document.get("label") or query),
                    "match_type": "exact" if exact else "suggested",
                }
    return None


def resolve_id(hpo_id):
    """Resolve an exact, current HPO identifier and its authoritative label."""
    identifier = str(hpo_id or "").strip().upper()
    if not re.fullmatch(r"HP:\d{7}", identifier):
        return None
    for document in _search(identifier, True):
        if (
            str(document.get("obo_id") or "").upper() == identifier
            and not document.get("is_obsolete")
        ):
            return {
                "hpo_id": identifier,
                "label": str(document.get("label") or ""),
                "match_type": "exact",
            }
    return None


def resolve_candidates(candidates):
    resolved = []
    seen = set()
    for candidate in candidates:
        term = resolve_label(candidate.get("label"))
        if not term or term["hpo_id"] in seen:
            continue
        seen.add(term["hpo_id"])
        resolved.append(
            {
                **term,
                "extracted_label": str(candidate.get("label") or ""),
                "source_text": str(candidate.get("source_text") or ""),
            }
        )
    return resolved