"""Human Phenotype Ontology term resolution through EMBL-EBI OLS4."""

import re

import requests
from app import togomcp_client


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


def resolve_candidates_via_ols4mcp(candidates):
    """Resolve only user-approved phenotype labels through OLS4MCP."""
    def documents_from_payload(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        response = payload.get("response")
        if isinstance(response, dict) and isinstance(response.get("docs"), list):
            return response["docs"]
        for key in ("docs", "results", "items", "classes"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        result = payload.get("result")
        if isinstance(result, dict):
            return documents_from_payload(result)
        return []

    resolved = []
    seen = set()
    approved = [
        candidate for candidate in candidates
        if str(candidate.get("label") or "").strip()
    ]
    payloads = togomcp_client.search_ols4_classes_many(
        [candidate["label"] for candidate in approved]
    )
    for candidate, payload in zip(approved, payloads):
        query = str(candidate.get("label") or "").strip()
        documents = documents_from_payload(payload)
        for document in documents or []:
            if not isinstance(document, dict):
                continue
            raw_id = str(
                document.get("obo_id") or document.get("oboId") or
                document.get("short_form") or document.get("id") or
                document.get("iri") or ""
            )
            hpo_match = re.search(r"HP[_:]\d{7}", raw_id, re.IGNORECASE)
            hpo_id = hpo_match.group(0).replace("_", ":").upper() if hpo_match else ""
            if not re.fullmatch(r"HP:\d{7}", hpo_id) or hpo_id in seen:
                continue
            if document.get("is_obsolete") or document.get("isObsolete"):
                continue
            seen.add(hpo_id)
            resolved.append({
                "hpo_id": hpo_id,
                "label": str(document.get("label") or document.get("prefLabel") or query),
                "match_type": "suggested",
                "extracted_label": query,
                "source_text": str(candidate.get("source_text") or ""),
            })
            break
    return resolved