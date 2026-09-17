"""Adapter for the priority rules in filter_variants.py.

The original script remains untouched. This module reuses its ClinVar and
gnomAD scoring functions for variants already stored in the database.
"""

import runpy
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).with_name("filter_variants.py")
_rules_cache = None
_rules_mtime_ns = None
_DISPLAY_INFO_KEYS = (
    "CLNSIG", "REVIEW_STAR", "CLNREVSTAT", "MANE_HIT", "VEP_IMPACT",
    "GNOMAD_AF", "GNOMAD_AF_GRPMAX", "GNOMAD_AF_EAS", "GNOMAD_AF_SAS",
    "gnomAD_AF_POPMAX", "REVEL", "CADD", "CADD_PHRED",
    "SpliceAI_AG", "SpliceAI_AL", "SpliceAI_DG", "SpliceAI_DL",
    "AlphaMissense", "AF",
)


def _load_rules():
    """Load the current script so replacements are used without code changes here."""
    global _rules_cache, _rules_mtime_ns
    mtime_ns = _SCRIPT_PATH.stat().st_mtime_ns
    if _rules_cache is not None and _rules_mtime_ns == mtime_ns:
        return _rules_cache

    original_argv = sys.argv
    try:
        sys.argv = [str(_SCRIPT_PATH), ""]
        _rules_cache = runpy.run_path(
            str(_SCRIPT_PATH), run_name="expertboard_filter_rules"
        )
        _rules_mtime_ns = mtime_ns
        return _rules_cache
    finally:
        sys.argv = original_argv


def _info_value(info, key):
    for item in (info or "").split(";"):
        name, separator, value = item.partition("=")
        if separator and name.upper() == key.upper():
            return value
    return None


def display_info_values(variant):
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
    return raw_values


def display_rule_scores(variant):
    """Return all scoring function results, including currently stubbed zeros."""
    rules = _load_rules()
    info = _scoring_info(variant)
    try:
        clinvar_score = rules["score_clinvar"](info)[0]
    except (IndexError, KeyError, TypeError, ValueError):
        clinvar_score = -1
    try:
        gnomad_score = rules["score_gnomad"](info)[0]
    except (IndexError, KeyError, TypeError, ValueError):
        gnomad_score = -1
    scores = {
        "score_clinvar": clinvar_score,
        "score_gnomad": gnomad_score,
    }
    for name in ("score_alphamissense", "score_cadd", "score_revel", "score_spliceai"):
        try:
            scores[name] = rules[name](info)
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


def _scoring_info(variant):
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

    return ";".join(fields)


def _evaluation_priority(variant, rules):
    """Return the original script's rank using already-loaded rules."""
    info = _scoring_info(variant)
    try:
        clinvar_score, _clnsig = rules["score_clinvar"](info)
        gnomad_score, _af, _grpmax, _eas, _sas = rules["score_gnomad"](info)
    except (IndexError, KeyError, TypeError, ValueError):
        clinvar_score = -1
        gnomad_score = -1

    impact = (_info_value(info, "VEP_IMPACT") or "").upper()
    if clinvar_score == 5:
        rank = 1
    elif clinvar_score > 1:
        rank = {3: 2, 2: 3, 1: 4}.get(gnomad_score, 5)
    elif clinvar_score == -1:
        rank = 5 if impact in ("HIGH", "MODERATE") else 6
    elif clinvar_score == 1:
        rank = 7
    else:
        rank = 8
    return rank


def evaluation_priority(variant):
    """Return the current script's rank, with missing fields ranked last."""
    return _evaluation_priority(variant, _load_rules())


def evaluation_priorities(variants):
    """Calculate ranks for one page using one current script load."""
    rules = _load_rules()
    return {variant.id: _evaluation_priority(variant, rules) for variant in variants}