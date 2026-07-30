"""TogoVar API client (GRCh38).

Looks up a variant by genomic position and returns:
- Clinical significance from ClinVar and MGeND
- Japanese allele frequencies (GEM-J WGA, ToMMo)
- AlphaMissense pathogenicity score
- Direct TogoVar link

API base: https://grch38.togovar.org/api
"""

import logging

import requests

TOGOVAR_BASE = "https://grch38.togovar.org/api"
TOGOVAR_VARIANT_PAGE = "https://grch38.togovar.org/variant/{tgv_id}"

TIMEOUT = 10

# Pathogenicity priority for ranking (higher = more severe)
_PATHOGENICITY_RANK = {
    "pathogenic": 7,
    "likely pathogenic": 6,
    "pathogenic/likely pathogenic": 6,
    "drug response": 5,
    "risk factor": 4,
    "uncertain significance": 3,
    "likely benign": 2,
    "benign": 1,
    "benign/likely benign": 1,
    "not provided": 0,
}

_INTERP_CSS = {
    "pathogenic":                   "togovar-p",
    "likely pathogenic":            "togovar-lp",
    "pathogenic/likely pathogenic": "togovar-lp",
    "uncertain significance":       "togovar-vus",
    "likely benign":                "togovar-lb",
    "benign":                       "togovar-b",
    "benign/likely benign":         "togovar-b",
    "drug response":                "togovar-dr",
    "risk factor":                  "togovar-rf",
}


def _normalise_chrom(chrom):
    """Strip 'chr' prefix; map 'M' → 'MT'."""
    c = str(chrom).strip()
    if c.upper().startswith("CHR"):
        c = c[3:]
    if c.upper() == "M":
        c = "MT"
    return c


def _highest_interpretation(interpretations):
    """Return the interpretation with the highest pathogenicity rank."""
    best = None
    best_rank = -1
    for interp in interpretations:
        rank = _PATHOGENICITY_RANK.get(interp.lower(), -1)
        if rank > best_rank:
            best_rank = rank
            best = interp
    return best


def _extract_frequency(frequencies, source_name):
    """
    Extract allele frequency for a given source from the frequencies payload.
    Handles both list-of-objects and dict formats.
    """
    if not frequencies:
        return None

    # list of {source: str, allele: {frequency: float}, ...}
    if isinstance(frequencies, list):
        for f in frequencies:
            if isinstance(f, dict) and f.get("source") == source_name:
                allele = f.get("allele") or {}
                freq = allele.get("frequency")
                if freq is not None:
                    return float(freq)
    elif isinstance(frequencies, dict):
        # keyed by source name
        entry = frequencies.get(source_name)
        if entry:
            allele = entry.get("allele") or {}
            freq = allele.get("frequency")
            if freq is not None:
                return float(freq)
    return None


def lookup_variant(chrom, pos, ref, alt):
    """
    Look up variant in TogoVar API by position (GRCh38).

    Returns a dict on success, None on not found, or raises on network error.

    Return keys:
      tgv_id         : str | None  — TogoVar internal ID
      significance   : list[{condition, interpretations}]
      all_interps    : list[str]   — flattened interpretations across all conditions
      top_interp     : str | None  — highest-ranked interpretation
      top_interp_css : str         — CSS class for colour coding
      gem_j_af       : float | None — GEM-J WGA allele frequency
      tommo_af       : float | None — ToMMo allele frequency
      alphamissense  : float | None
      togovar_url    : str | None
    """
    chrom_clean = _normalise_chrom(chrom)
    try:
        resp = requests.post(
            f"{TOGOVAR_BASE}/search/variant",
            json={
                "query": {
                    "location": {
                        "chromosome": chrom_clean,
                        "position": int(pos),
                    }
                },
                "limit": 100,
            },
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logging.warning("TogoVar lookup failed: %s", exc)
        raise

    payload = resp.json()
    items = payload.get("data") or []

    for item in items:
        if item.get("reference") == ref and item.get("alternative") == alt:
            tgv_id = item.get("id")
            sigs = item.get("significance") or []

            all_interps = []
            for s in sigs:
                all_interps.extend(s.get("interpretations") or [])

            top = _highest_interpretation(all_interps)

            gem_j = _extract_frequency(item.get("frequencies"), "gem_j_wga")
            tommo  = _extract_frequency(item.get("frequencies"), "tommo")

            am_raw = item.get("alphamissense")
            am = None
            if am_raw is not None:
                try:
                    am = float(am_raw)
                except (TypeError, ValueError):
                    pass

            return {
                "tgv_id":         tgv_id,
                "significance":   sigs,
                "all_interps":    all_interps,
                "top_interp":     top,
                "top_interp_css": _INTERP_CSS.get((top or "").lower(), "togovar-other"),
                "gem_j_af":       gem_j,
                "tommo_af":       tommo,
                "alphamissense":  am,
                "togovar_url":    TOGOVAR_VARIANT_PAGE.format(tgv_id=tgv_id) if tgv_id else None,
            }

    return None  # not found at this position/allele
