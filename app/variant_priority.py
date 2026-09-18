"""Adapter for the priority rules in filter_variants.py.

Reimplements the same scoring logic natively instead of executing
filter_variants.py, so this module has no dependency on that script's
presence or exact on-disk form.
"""

_AF_THRESHOLD = 0.05  # gnomAD allele frequency threshold used by score_gnomad

_DISPLAY_INFO_KEYS = (
    "CLNSIG", "REVIEW_STAR", "CLNREVSTAT", "MANE_HIT", "VEP_IMPACT",
    "GNOMAD_AF", "GNOMAD_AF_GRPMAX", "GNOMAD_AF_EAS", "GNOMAD_AF_SAS",
    "gnomAD_AF_POPMAX", "REVEL", "CADD", "CADD_PHRED",
    "SpliceAI_AG", "SpliceAI_AL", "SpliceAI_DG", "SpliceAI_DL",
    "AlphaMissense", "AF",
)


_MISSING_AF_TOKENS = {"", "-", "na", "n/a", ".", "null", "none"}


def _parse_review_star(value):
    """Treat a missing/non-value REVIEW_STAR (absent, 0, -, NA, .) as 0 stars."""
    value = (value or "").strip()
    if value.lower() in _MISSING_AF_TOKENS:
        return 0
    return int(value)


def _score_clinvar(info):
    """score will be 0-4, with 4 being the highest priority."""
    try:
        clnsig = info.split("CLNSIG=")[1].split(";")[0]
        review_star = _parse_review_star(_info_value(info, "REVIEW_STAR"))

        if clnsig in ("Pathogenic", "Likely_pathogenic"):
            if review_star >= 3:  # expert panel (3) or practice guidelines (4)
                score = 4
            elif review_star >= 1:  # single (1) or multiple (2) submitters
                score = 3
            else:  # review_star == 0, no evidence / conflicting
                score = 2
        elif clnsig == "Uncertain_significance":
            score = 1
        else:  # Benign or Likely_benign
            score = 0
    except (IndexError, ValueError):
        clnsig = "."
        score = -1
    return score, clnsig


def _parse_af(value):
    """Treat gnomAD 'not observed'/missing tokens (0, -, NA, .) as AF=0."""
    value = (value or "").strip()
    if value.lower() in _MISSING_AF_TOKENS:
        return 0.0
    return float(value)


def _score_gnomad(info):
    """score will be 0-3, with 3 being the highest priority."""
    try:
        # A field missing entirely (variant not found in gnomAD at all) is
        # treated the same as an explicit 0/-/NA: not observed = rare.
        gnomad_af = _parse_af(_info_value(info, "GNOMAD_AF"))
        gnomad_af_grpmax = _parse_af(_info_value(info, "GNOMAD_AF_GRPMAX"))
        gnomad_af_eas = _parse_af(_info_value(info, "GNOMAD_AF_EAS"))
        gnomad_af_sas = _parse_af(_info_value(info, "GNOMAD_AF_SAS"))

        if gnomad_af_grpmax <= _AF_THRESHOLD:  # low AF in all populations, prioritize
            score = 3
        elif gnomad_af_eas <= _AF_THRESHOLD and gnomad_af_sas <= _AF_THRESHOLD:
            score = 2
        elif gnomad_af_eas <= _AF_THRESHOLD or gnomad_af_sas <= _AF_THRESHOLD:
            score = 1
        else:
            score = 0
    except (TypeError, ValueError):
        gnomad_af = gnomad_af_grpmax = gnomad_af_eas = gnomad_af_sas = "."
        score = -1
    return score, gnomad_af, gnomad_af_grpmax, gnomad_af_eas, gnomad_af_sas


def _score_alphamissense(info):
    return 0


def _score_cadd(info):
    return 0


def _score_revel(info):
    return 0


def _score_spliceai(info):
    return 0


def _score_priority(info):
    """Return the Francis priority rank for one VCF INFO string."""
    clinvar_score = _score_clinvar(info)[0]
    gnomad_score = _score_gnomad(info)[0]
    impact = info.split("VEP_IMPACT=")[1].split(";")[0]

    if clinvar_score == 4:
        return 1
    if clinvar_score > 0:
        return {3: 2, 2: 3, 1: 4}.get(gnomad_score, 5)
    if clinvar_score == -1:
        return 5 if impact in ("HIGH", "MODERATE") else 6
    # Benign / Likely_benign: split by ClinVar review confidence.
    try:
        review_star = int(info.split("REVIEW_STAR=")[1].split(";")[0])
    except (IndexError, ValueError):
        review_star = 0
    return 8 if review_star >= 3 else 7


def _info_value(info, key):
    for item in (info or "").split(";"):
        name, separator, value = item.partition("=")
        if separator and name.upper() == key.upper():
            return value
    return None


def live_annotation_info(annotation, alt=None):
    """Map live VEP fields into the INFO names used by Francis rules."""
    annotation = annotation or {}
    vep = annotation.get("vep") or {}
    transcripts = vep.get("transcript_consequences") or []
    transcript = next(
        (
            item for item in transcripts
            if item.get("mane_select") or item.get("mane_plus_clinical")
        ),
        None,
    ) or (transcripts[0] if transcripts else {})
    values = {}
    mappings = {
        "VEP_IMPACT": "impact",
        "VEP_HGVSC": "hgvsc",
        "VEP_HGVSP": "hgvsp",
        "REVEL": "revel_score",
        "CADD_PHRED": "cadd_phred",
        "AlphaMissense": "alphamissense",
    }
    for info_key, vep_key in mappings.items():
        value = transcript.get(vep_key)
        if value not in (None, "", "."):
            values[info_key] = value
    if transcript.get("mane_select") or transcript.get("mane_plus_clinical"):
        values["MANE_HIT"] = "Yes"
    spliceai = transcript.get("spliceai") or {}
    if isinstance(spliceai, dict):
        for suffix in ("AG", "AL", "DG", "DL"):
            value = spliceai.get(suffix)
            if value not in (None, "", "."):
                values[f"SpliceAI_{suffix}"] = value
    values.update(_gnomad_frequency_info(vep, alt))
    return values


def _gnomad_frequency_info(vep, alt):
    """Map VEP colocated_variants[].frequencies (needs af_gnomad=1) to score_gnomad()'s INFO keys."""
    frequencies = None
    alt = (alt or "").upper() or None
    for item in vep.get("colocated_variants") or []:
        freqs = item.get("frequencies")
        if not isinstance(freqs, dict):
            continue
        if alt and alt in freqs:
            frequencies = freqs[alt]
            break
        if frequencies is None and freqs:
            frequencies = next(iter(freqs.values()), None)
    if not isinstance(frequencies, dict):
        return {}

    def _max(*keys):
        values = [frequencies[key] for key in keys if isinstance(frequencies.get(key), (int, float))]
        return max(values) if values else None

    values = {}
    overall = _max("gnomade", "gnomadg")
    eas = _max("gnomade_eas", "gnomadg_eas")
    sas = _max("gnomade_sas", "gnomadg_sas")
    # gnomAD's "grpmax": the highest AF among major population groups (exomes or genomes).
    grpmax = None
    for pop in ("afr", "amr", "eas", "sas", "nfe", "fin", "asj", "mid", "ami", "remaining"):
        pop_max = _max(f"gnomade_{pop}", f"gnomadg_{pop}")
        if pop_max is not None and (grpmax is None or pop_max > grpmax):
            grpmax = pop_max
    if overall is not None:
        values["GNOMAD_AF"] = overall
    if grpmax is not None:
        values["GNOMAD_AF_GRPMAX"] = grpmax
    if eas is not None:
        values["GNOMAD_AF_EAS"] = eas
    if sas is not None:
        values["GNOMAD_AF_SAS"] = sas
    return values


def clinvar_info(annotation):
    """Map persisted ClinVar summary data to Francis INFO fields."""
    annotation = annotation or {}
    summary = annotation.get("summary") or {}
    submissions = annotation.get("submissions") or []
    values = {}
    # Current NCBI esummary (v2.0) nests classification under "germline_classification";
    # older responses used "clinical_significance".
    significance_raw = summary.get("germline_classification") or summary.get("clinical_significance")
    significance_dict = significance_raw if isinstance(significance_raw, dict) else None
    significance = (
        significance_dict.get("description") or significance_dict.get("value")
        if significance_dict else significance_raw
    )
    if not significance:
        significance = next(
            (item.get("clinical_significance") for item in submissions
             if isinstance(item, dict) and item.get("clinical_significance")),
            None,
        )
    if significance:
        normalized = str(significance).strip().lower().replace(" ", "_")
        values["CLNSIG"] = {
            "pathogenic": "Pathogenic",
            "likely_pathogenic": "Likely_pathogenic",
            "uncertain_significance": "Uncertain_significance",
            "likely_benign": "Likely_benign",
            "benign": "Benign",
        }.get(normalized, str(significance))

    # NCBI esummary nests review_status inside germline_classification (or
    # clinical_significance for older responses).
    review_status = summary.get("review_status") or summary.get("review_status_description")
    if not review_status and significance_dict:
        review_status = (
            significance_dict.get("review_status")
            or significance_dict.get("review_status_description")
        )
    if not review_status:
        review_status = next(
            (item.get("review_status") for item in submissions
             if isinstance(item, dict) and item.get("review_status")),
            None,
        )
    statuses = [review_status] if review_status else []
    statuses.extend(
        item.get("review_status") for item in submissions
        if isinstance(item, dict) and item.get("review_status")
    )
    stars = 0
    for raw_status in statuses:
        status = str(raw_status).lower()
        candidate = 4 if "practice guideline" in status else (
            3 if "expert panel" in status else (
                2 if "multiple submitters" in status else (
                    1 if "single submitter" in status else 0
                )
            )
        )
        stars = max(stars, candidate)
    if review_status:
        values["CLNREVSTAT"] = str(review_status)
    if statuses:
        values["REVIEW_STAR"] = str(stars)
    return values


def display_info_values(variant, annotation=None, clinvar_annotation=None):
    """Return the Francis script's INFO fields for display in the patient table."""
    raw_values = {}
    for item in (variant.raw_info or "").split(";"):
        name, separator, value = item.partition("=")
        if not separator or value in ("", "."):
            continue
        for display_name in _DISPLAY_INFO_KEYS:
            if name.upper() == display_name.upper():
                raw_values[display_name] = value
                break
    if "CLNSIG" not in raw_values and variant.clin_sig:
        raw_values["CLNSIG"] = variant.clin_sig
    raw_values.update(live_annotation_info(annotation, variant.alt))
    raw_values.update(clinvar_info(clinvar_annotation))
    return raw_values


def display_rule_scores(variant, annotation=None, clinvar_annotation=None):
    """Return all scoring function results, including currently stubbed zeros."""
    info = _scoring_info(variant, annotation, clinvar_annotation)
    try:
        clinvar_score = _score_clinvar(info)[0]
    except (IndexError, KeyError, TypeError, ValueError):
        clinvar_score = -1
    try:
        gnomad_score = _score_gnomad(info)[0]
    except (IndexError, KeyError, TypeError, ValueError):
        gnomad_score = -1
    scores = {
        "score_clinvar": clinvar_score,
        "score_gnomad": gnomad_score,
    }
    for name, scorer in (
        ("score_alphamissense", _score_alphamissense),
        ("score_cadd", _score_cadd),
        ("score_revel", _score_revel),
        ("score_spliceai", _score_spliceai),
    ):
        try:
            scores[name] = scorer(info)
        except (IndexError, KeyError, TypeError, ValueError):
            scores[name] = "error"
    return scores


def _canonical_clnsig(value):
    labels = {
        "pathogenic": "Pathogenic",
        "likely_pathogenic": "Likely_pathogenic",
        "uncertain_significance": "Uncertain_significance",
        "likely_benign": "Likely_benign",
        "benign": "Benign",
    }
    return labels.get((value or "").strip().lower().replace(" ", "_"), value)


def _scoring_info(variant, annotation=None, clinvar_annotation=None):
    """Build the INFO input expected by the original scoring script."""
    info = variant.raw_info or ""
    fields = [] if not info else info.split(";")

    clnsig = _info_value(info, "CLNSIG")
    if clnsig is None and variant.clin_sig:
        fields.append(f"CLNSIG={_canonical_clnsig(variant.clin_sig)}")
    elif clnsig is not None:
        for index, field in enumerate(fields):
            if field.partition("=")[0].upper() == "CLNSIG":
                fields[index] = f"CLNSIG={_canonical_clnsig(clnsig)}"
                break
    if _info_value(info, "REVIEW_STAR") is None and _info_value(
        ";".join(fields), "CLNSIG"
    ) is not None:
        fields.append("REVIEW_STAR=0")

    live_values = live_annotation_info(annotation, variant.alt)
    live_values.update(clinvar_info(clinvar_annotation))
    for key, value in live_values.items():
        fields = [
            field for field in fields
            if field.partition("=")[0].upper() != key.upper()
        ]
        fields.append(f"{key}={value}")
    return ";".join(fields)


def _evaluation_priority(variant, annotation=None, clinvar_annotation=None):
    """Return the priority from the original Francis filter implementation."""
    info = _scoring_info(variant, annotation, clinvar_annotation)
    try:
        return _score_priority(info)
    except (IndexError, KeyError, TypeError, ValueError):
        # Preserve the original filter's fallback behavior for incomplete VCFs.
        return 6


def evaluation_priority(variant, annotation=None, clinvar_annotation=None):
    """Return the current script's rank, with missing fields ranked last."""
    return _evaluation_priority(variant, annotation, clinvar_annotation)


def evaluation_priorities(variants, annotations_by_variant=None, clinvar_by_variant=None):
    """Calculate ranks for every variant on a page."""
    annotations_by_variant = annotations_by_variant or {}
    clinvar_by_variant = clinvar_by_variant or {}
    return {
        variant.id: _evaluation_priority(
            variant, annotations_by_variant.get(variant.id),
            clinvar_by_variant.get(variant.id)
        )
        for variant in variants
    }