"""Small NCBI ClinVar E-utilities client for reviewer evidence."""

import re
import threading
import time
import xml.etree.ElementTree as ET

import requests


EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 30
# NCBI allows ~3 requests/second without an API key; bulk refreshes issue
# several requests per variant (esearch/esummary/efetch), so throttle every
# outbound call to avoid 429s that would silently skip later variants.
_RATE_LIMIT_INTERVAL = 0.35
_rate_lock = threading.Lock()
_last_request_time = 0.0


def _throttle():
    global _last_request_time
    with _rate_lock:
        wait = _RATE_LIMIT_INTERVAL - (time.monotonic() - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()


def _get(path, params):
    _throttle()
    response = requests.get(
        f"{EUTILS_BASE_URL}/{path}",
        params={**params, "db": "clinvar", "retmode": "json"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _summary(ids):
    if not ids:
        return None
    payload = _get("esummary.fcgi", {"id": ",".join(ids), "version": "2.0"})
    result = payload.get("result") or {}
    for identifier in ids:
        record = result.get(str(identifier))
        # NCBI returns {"uid": ..., "error": "..."} for ids it can't resolve.
        if isinstance(record, dict) and not record.get("error"):
            return record
    return None


def _search_ids(term):
    payload = _get("esearch.fcgi", {"term": term})
    return (payload.get("esearchresult") or {}).get("idlist") or []


def _fetch_xml(ids):
    if not ids:
        return None
    _throttle()
    response = requests.get(
        f"{EUTILS_BASE_URL}/efetch.fcgi",
        params={"db": "clinvar", "id": ",".join(ids), "rettype": "vcv", "retmode": "xml"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _first_text(element, names):
    names = {name.lower() for name in names}
    for child in element.iter():
        if _local_name(child.tag) in names and (child.text or "").strip():
            return " ".join("".join(child.itertext()).split())
    return ""


def _extract_submissions(xml_text):
    """Extract SCV-like ClinVar assertions needed for PM3/PP1 review."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    assertions = [
        element for element in root.iter()
        if _local_name(element.tag) == "clinicalassertion"
    ]
    submissions = []
    for assertion in assertions:
        comment = _first_text(assertion, {"comment", "description"})
        condition = _first_text(assertion, {"condition", "trait", "traitname"})
        origin = _first_text(assertion, {"origin", "alleleorigin"})
        significance = _first_text(
            assertion, {"clinicalsignificance", "clinicalsignificancevalue"}
        )
        review_status = _first_text(assertion, {"reviewstatus", "reviewstatusdescription"})
        submitter = _first_text(assertion, {"submitter", "organization", "submittername"})
        text = " ".join(
            value for value in (comment, condition, origin, significance, review_status, submitter)
            if value
        ).lower()
        keywords = [
            keyword for keyword in (
                "in trans", "compound heterozygous", "biallelic",
                "opposite alleles", "segregates with disease",
                "co-segregation", "affected relatives", "unaffected relatives",
            ) if keyword in text
        ]
        submissions.append({
            "submitter": submitter,
            "condition": condition,
            "origin": origin,
            "clinical_significance": significance,
            "review_status": review_status,
            "comment": comment,
            "keywords": keywords,
        })
    return submissions


def fetch_variant(variant):
    """Fetch ClinVar using HGVS first and only validated accession formats."""
    external_id = str(variant.variant_ext_id or "").strip()
    vcv_id = re.fullmatch(r"VCV\d+(?:\.\d+)?", external_id, re.IGNORECASE)
    rs_id = re.fullmatch(r"rs\d+", external_id, re.IGNORECASE)
    numeric_uid = re.fullmatch(r"\d+", external_id)
    if numeric_uid:
        ids = [external_id]
        record = _summary(ids)
        if record is not None:
            return {
                "query": external_id,
                "search_type": "clinvar_uid",
                "search_ids": ids,
                "clinvar_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{external_id}/",
                "summary": record,
                "submissions": _extract_submissions(_fetch_xml(ids)),
            }
        # Not a real ClinVar UID; VCFs commonly store dbSNP rs numbers here
        # without the "rs" prefix, so retry as an rs ID search.
        rs_query = f"rs{external_id}"
        ids = _search_ids(rs_query)
        record = _summary(ids[:1])
        return {
            "query": rs_query,
            "search_type": "rs",
            "search_ids": ids[:10],
            "summary": record,
            "submissions": _extract_submissions(_fetch_xml(ids[:1])) if record else [],
        }
    if vcv_id:
        ids = _search_ids(f"{external_id}[Accession]")
        if not ids:
            ids = _search_ids(external_id)
        if not ids:
            match = re.fullmatch(r"VCV(\d+)(?:\.\d+)?", external_id, re.IGNORECASE)
            if match:
                ids = [match.group(1).lstrip("0") or "0"]
        record = _summary(ids[:1])
        submissions = _extract_submissions(_fetch_xml(ids[:1]))
        return {
            "query": external_id,
            "search_type": "vcv",
            "search_ids": ids[:10],
            "clinvar_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{ids[0]}/" if ids else None,
            "summary": record,
            "submissions": submissions,
        }

    queries = []
    if variant.hgvs_c:
        queries.append(variant.hgvs_c)
    if variant.gene and variant.hgvs_c:
        queries.append(f"{variant.gene}[gene] AND {variant.hgvs_c}")
    if rs_id:
        if variant.gene:
            queries.append(f"{variant.gene}[gene] AND {rs_id.group(0)}")
        queries.append(rs_id.group(0))
    if not queries:
        return {
            "query": "",
            "search_type": "none",
            "ignored_variant_id": external_id or None,
            "summary": None,
            "submissions": [],
        }

    for query in queries:
        search = _get("esearch.fcgi", {"term": query})
        ids = (search.get("esearchresult") or {}).get("idlist") or []
        record = _summary(ids[:1])
        if record:
            submissions = _extract_submissions(_fetch_xml(ids[:1]))
            return {
                "query": query,
                "search_type": "hgvs" if variant.hgvs_c else "rs",
                "search_ids": ids[:10],
                "summary": record,
                "submissions": submissions,
            }
    return {
        "query": queries[0],
        "search_type": "hgvs" if variant.hgvs_c else "rs",
        "summary": None,
        "submissions": [],
    }
