"""Small NCBI ClinVar E-utilities client for reviewer evidence."""

import re
import xml.etree.ElementTree as ET

import requests


EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 30


def _get(path, params):
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
        if isinstance(record, dict):
            return record
    return None


def _search_ids(term):
    payload = _get("esearch.fcgi", {"term": term})
    return (payload.get("esearchresult") or {}).get("idlist") or []


def _fetch_xml(ids):
    if not ids:
        return None
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
    """Fetch a ClinVar summary using a VCV accession or HGVS search."""
    external_id = str(variant.variant_ext_id or "").strip()
    if external_id.upper().startswith("VCV"):
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
            "summary": record,
            "submissions": submissions,
        }

    queries = []
    if variant.hgvs_c:
        queries.append(variant.hgvs_c)
    if variant.gene and variant.hgvs_c:
        queries.append(f"{variant.gene}[gene] AND {variant.hgvs_c}")
    if external_id:
        if variant.gene:
            queries.append(f"{variant.gene}[gene] AND {external_id}")
        queries.append(external_id)
    if not queries:
        return {"query": "", "search_type": "none", "summary": None}

    for query in queries:
        search = _get("esearch.fcgi", {"term": query})
        ids = (search.get("esearchresult") or {}).get("idlist") or []
        record = _summary(ids[:1])
        if record:
            submissions = _extract_submissions(_fetch_xml(ids[:1]))
            return {
                "query": query,
                "search_type": "hgvs",
                "search_ids": ids[:10],
                "summary": record,
                "submissions": submissions,
            }
    return {"query": queries[0], "search_type": "hgvs", "summary": None, "submissions": []}
