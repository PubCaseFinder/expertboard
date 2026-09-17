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


def _evaluation_priority(variant, rules):
    """Return the original script's rank using already-loaded rules."""
    info = variant.raw_info or ""
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