"""Variant assessment CRUD.

Each assessment records one expert group's classification of a single variant.
Different groups (e.g. Japan Rare Disease Panel, Singapore Medical Genetics)
may hold different classifications for the same variant, enabling side-by-side
country/group comparison on the patient detail page.
"""

import json

from sqlalchemy import asc

from app.db import Session
from app.models import ExpertBoard
from app.models import Patient
from app.models import Variant
from app.models import VariantAssessment


CLASSIFICATIONS = [
    ("Pathogenic",            "Pathogenic"),
    ("Likely pathogenic",     "Likely pathogenic"),
    ("Uncertain significance","Uncertain significance (VUS)"),
    ("Likely benign",         "Likely benign"),
    ("Benign",                "Benign")
]

PRIOR_PROBABILITY = 0.102
EVIDENCE_STRENGTH_UNIT = 2.0801

STRENGTH_POINTS = {
    "VeryStrong": 8,
    "Strong": 4,
    "Moderate": 2,
    "Supporting": 1,
    "Indeterminate": 0,
    "StandAlone": 8,
}

EVIDENCE_LEVELS = [
    ("",            "—"),
    ("strong",      "Strong"),
    ("moderate",    "Moderate"),
    ("supporting",  "Supporting"),
]

ACMG_CODES = [
    # Pathogenic criteria
    ("PVS1", "PVS1 (Very strong: Null variant)"),
    ("PS1",  "PS1 (Strong: Same amino acid change)"),
    ("PS2",  "PS2 (Strong: De novo confirmed)"),
    ("PS3",  "PS3 (Strong: Functional study)"),
    ("PS4",  "PS4 (Strong: Prevalence in affected)"),
    ("PM1",  "PM1 (Moderate: Mutational hot spot)"),
    # The ClinGen Sequence Variant Interpretation (SVI) Working Group has re-adjusted PM2 to be supporting level as of 2020 \
    # (https://www.clinicalgenome.org/site/assets/files/5182/pm2_-_svi_recommendation_-_approved_sept2020.pdf)
    ("PM2",  "PM2 (Supporting: Absent/low in control DB)"),
    ("PM3",  "PM3 (Moderate: In trans with pathogenic)"),
    ("PM4",  "PM4 (Moderate: Protein length change)"),
    ("PM5",  "PM5 (Moderate: Novel missense at same AA)"),
    ("PM6",  "PM6 (Moderate: De novo assumed)"),
    ("PP1",  "PP1 (Supporting: Co-segregation)"),
    ("PP2",  "PP2 (Supporting: Missense in constrained gene)"),
    ("PP3",  "PP3 (Supporting: Multiple computational evidence)"),
    ("PP4",  "PP4 (Supporting: Specific phenotype fit)"),
    # Benign criteria
    ("BA1",  "BA1 (Stand-alone: High allele frequency >5%)"),
    ("BS1",  "BS1 (Strong: Allele frequency > expected)"),
    ("BS2",  "BS2 (Strong: Observed in healthy)"),
    ("BS3",  "BS3 (Strong: Functional study non-pathogenic)"),
    ("BS4",  "BS4 (Strong: Lack of segregation)"),
    ("BP1",  "BP1 (Supporting: Non-deleterious missense)"),
    ("BP2",  "BP2 (Supporting: In trans with dominant / cis)"),
    ("BP3",  "BP3 (Supporting: In-frame indel in repeat)"),
    ("BP4",  "BP4 (Supporting: Computational prediction benign)"),
    ("BP5",  "BP5 (Supporting: Alternate cause found)"),
    ("BP7",  "BP7 (Supporting: Silent/synonymous no splice effect)"),
]

ACMG_DEFAULT_WEIGHTS = {
    "PVS1": "VeryStrong",
    "PS1": "Strong",
    "PS2": "Strong",
    "PS3": "Strong",
    "PS4": "Strong",
    "PM1": "Moderate",
    "PM2": "Supporting",
    "PM3": "Moderate",
    "PM4": "Moderate",
    "PM5": "Moderate",
    "PM6": "Moderate",
    "PP1": "Supporting",
    "PP2": "Supporting",
    "PP3": "Supporting",
    "PP4": "Supporting",
    "BA1": "VeryStrong",
    "BS1": "Strong",
    "BS2": "Strong",
    "BS3": "Strong",
    "BS4": "Strong",
    "BP1": "Supporting",
    "BP2": "Supporting",
    "BP3": "Supporting",
    "BP4": "Supporting",
    "BP5": "Supporting",
    "BP7": "Supporting",
}

ACMG_WEIGHT_OPTIONS = {
    "PVS1": [
        ("", "Very Strong"),
        ("Strong", "Strong"),
        ("Moderate", "Moderate"),
        ("Supporting", "Supporting"),
    ],
    "PS1": [
        ("", "Strong"),
        ("Moderate", "Moderate"),
        ("Supporting", "Supporting"),
    ],
    "PS2": [
        ("", "Strong"),
        ("VeryStrong", "Very Strong"),
        ("Moderate", "Moderate"),
        ("Supporting", "Supporting")
    ],
    "PS3": [
        ("", "Strong"),
        ("Moderate", "Moderate"),
        ("Supporting", "Supporting"),
    ],
    "PS4": [
        ("", "Strong"),
        ("Moderate", "Moderate"),
        ("Supporting", "Supporting"),
    ],
    "PM1": [
        ("", "Moderate"),
        ("Strong", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "PM2": [
        ("Supporting", "Supporting"),
        ("Moderate", "Moderate"),
        ("Strong", "Strong"),
        ("VeryStrong", "Very Strong")
    ],
    "PM3": [
        ("", "Moderate"),
        ("VeryStrong", "Very Strong"),
    ],
    "PM4": [
        ("", "Moderate"),
        ("Strong", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "PM5": [
        ("", "Moderate"),
        ("Strong", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "PM6": [
        ("", "Moderate"),
        ("Strong", "Strong"),
        ("VeryStrong", "Very Strong"),
    ],
    "PP1": [("", "Supporting"), ("Moderate","Moderate"), ("Strong", "Strong")],
    "PP2": [("", "Supporting")],
    "PP3": [("", "Supporting"), ("Moderate","Moderate"), ("Strong", "Strong")],
    "PP4": [("", "Supporting"), ("Moderate","Moderate"), ("Strong", "Strong")],
    "BA1": [("", "Very Strong")],
    "BS1": [
        ("", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "BS2": [
        ("", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "BS3": [
        ("", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "BS4": [
        ("", "Strong"),
        ("Supporting", "Supporting"),
    ],
    "BP1": [("", "Supporting")],
    "BP2": [("", "Supporting")],
    "BP3": [("", "Supporting")],
    "BP4": [("", "Supporting"), ("Moderate","Moderate"), ("Strong", "Strong")],
    "BP5": [("", "Supporting")],
    "BP7": [("", "Supporting"), ("Strong", "Strong")],
}

for _weight_options in ACMG_WEIGHT_OPTIONS.values():
    _weight_options.append(("Indeterminate", "Indeterminate (0 points)"))

# CSS suffix used in template: assess-<key>
CLASSIFICATION_CSS = {
    "Pathogenic":             "p",
    "Likely pathogenic":      "lp",
    "Uncertain significance": "vus",
    "Likely benign":          "lb",
    "Benign":                 "b",
    "Other":                  "other",
}


def _normalize_strength(value):
    normalized = (value or "").replace(" ", "").replace("_", "").lower()
    return {
        "verystrong": "VeryStrong",
        "strong": "Strong",
        "moderate": "Moderate",
        "supporting": "Supporting",
        "indeterminate": "Indeterminate",
        "standalone": "StandAlone",
    }.get(normalized)


def parse_evidence(acmg_codes):
    """Convert stored ACMG tokens into individually scored evidence items."""
    valid_codes = {code for code, _label in ACMG_CODES}
    evidence = []
    for raw_token in (acmg_codes or "").split(","):
        token = raw_token.strip()
        if not token:
            continue
        code, separator, explicit_strength = token.partition("_")
        if code not in valid_codes:
            continue
        strength = _normalize_strength(explicit_strength if separator else "")
        strength = strength or ACMG_DEFAULT_WEIGHTS.get(code, "Supporting")
        magnitude = STRENGTH_POINTS[strength]
        points = -magnitude if code.startswith("B") else magnitude
        evidence.append({
            "code": code,
            "strength": strength,
            "points": points,
        })
    return evidence


def classify_score(total_score, reviewer_override=False):
    """Map a Tavtigian total score to an ACMG/AMP classification."""
    if total_score >= 10:
        return "Pathogenic"
    if total_score >= 6:
        return "Likely pathogenic"
    if total_score >= 0:
        return "Uncertain significance"
    if reviewer_override and total_score > -2:
        return "Uncertain significance"
    if total_score >= -6:
        return "Likely benign"
    return "Benign"


def calculate_assessment(evidence, reviewer_override=False):
    """Calculate score, posterior probability, and classification."""
    total_score = sum(item["points"] for item in evidence)
    odds_pathogenicity = EVIDENCE_STRENGTH_UNIT ** total_score
    posterior_probability = (
        odds_pathogenicity * PRIOR_PROBABILITY
    ) / (
        odds_pathogenicity * PRIOR_PROBABILITY - PRIOR_PROBABILITY + 1
    )
    return {
        "evidence": evidence,
        "total_score": total_score,
        "posterior_probability": posterior_probability,
        "classification": classify_score(total_score, reviewer_override),
        "reviewer_override": bool(reviewer_override),
    }


def assessment_summary(assessment):
    """Recalculate an assessment from its individual evidence records."""
    try:
        evidence = json.loads(assessment.evidence_points or "[]")
    except (TypeError, ValueError):
        evidence = []
    if not evidence:
        evidence = parse_evidence(assessment.acmg_codes)
    return calculate_assessment(evidence, assessment.reviewer_override_lb_threshold)


def assessment_payload(assessment):
    """Return the calculated fields required by API and clinical report clients."""
    summary = assessment_summary(assessment)
    return {
        "id": assessment.id,
        "variant_id": assessment.variant_id,
        "classification": summary["classification"],
        "total_score": summary["total_score"],
        "posterior_probability": summary["posterior_probability"],
        "reviewer_override_lb_threshold": summary["reviewer_override"],
        "evidence": summary["evidence"],
    }


def list_for_variants(variant_ids):
    """Return {variant_id: [{"assessment": obj, "group": obj|None, "css": str}]}."""
    if not variant_ids:
        return {}
    session = Session()
    rows = (
        session.query(VariantAssessment)
        .filter(VariantAssessment.variant_id.in_(list(variant_ids)))
        .order_by(asc(VariantAssessment.variant_id), asc(VariantAssessment.id))
        .all()
    )
    result = {}
    for a in rows:
        group = session.get(ExpertBoard, a.expert_board_id) if a.expert_board_id else None
        score = assessment_summary(a)
        result.setdefault(a.variant_id, []).append(
            {
                "assessment": a,
                "group": group,
                "css": CLASSIFICATION_CSS.get(score["classification"], "other"),
                "score": score,
            }
        )
    return result


def add_assessment(
    variant_id,
    expert_board_id,
    classification,
    evidence_level,
    notes,
    assessed_by,
    acmg_codes=None,
    reviewer_override=False,
):
    """Create an assessment. Returns (assessment, error)."""
    evidence = parse_evidence(acmg_codes)
    calculated = calculate_assessment(evidence, reviewer_override)

    raw_gid = str(expert_board_id or "").strip()
    gid = int(raw_gid) if raw_gid.isdigit() else None

    session = Session()
    if gid:
        if session.get(ExpertBoard, gid) is None:
            return None, "Expert board not found."

    a = VariantAssessment(
        variant_id=int(variant_id),
        expert_board_id=gid,
        classification=calculated["classification"],
        evidence_level=(evidence_level or "").strip() or None,
        acmg_codes=(acmg_codes or "").strip() or None,
        evidence_points=json.dumps(evidence, separators=(",", ":")),
        total_score=calculated["total_score"],
        posterior_probability=calculated["posterior_probability"],
        reviewer_override_lb_threshold=calculated["reviewer_override"],
        notes=(notes or "").strip() or None,
        assessed_by=(assessed_by or "").strip() or None,
    )
    session.add(a)
    session.commit()
    return a, None


def remove_assessment(assessment_id):
    """Delete an assessment row. Returns True if removed."""
    session = Session()
    a = session.get(VariantAssessment, assessment_id)
    if a is None:
        return False
    session.delete(a)
    session.commit()
    return True


def get_assessment(assessment_id):
    """Return one assessment by ID."""
    return Session().get(VariantAssessment, assessment_id)


def list_cross_patient_for_variants(proband_variants, patient_id):
    """Find assessments of the same genomic variant recorded for other patients.

    Returns {proband_variant_id: [{"assessment", "group", "patient", "css"}]}
    keyed by the proband's variant ID so the template can do a simple lookup.
    """
    if not proband_variants:
        return {}

    session = Session()

    # Map (chrom, pos, ref, alt) → proband variant ID for fast lookup
    key_to_pvid = {
        (v.chrom, v.pos, v.ref, v.alt): v.id for v in proband_variants
    }
    chroms = list({v.chrom for v in proband_variants})

    # Fetch other patients' variants on the same chromosomes, then filter exactly
    other_variants = (
        session.query(Variant)
        .filter(
            Variant.patient_id != patient_id,
            Variant.chrom.in_(chroms),
        )
        .all()
    )

    # variant_id → (proband_variant_id, other_patient_id)
    ov_map = {}
    for ov in other_variants:
        k = (ov.chrom, ov.pos, ov.ref, ov.alt)
        if k in key_to_pvid:
            ov_map[ov.id] = (key_to_pvid[k], ov.patient_id)

    if not ov_map:
        return {}

    assessment_rows = (
        session.query(VariantAssessment)
        .filter(VariantAssessment.variant_id.in_(list(ov_map.keys())))
        .order_by(asc(VariantAssessment.id))
        .all()
    )

    result = {}
    for a in assessment_rows:
        pvid, pat_id = ov_map[a.variant_id]
        group = session.get(ExpertBoard, a.expert_board_id) if a.expert_board_id else None
        patient = session.get(Patient, pat_id)
        score = assessment_summary(a)
        result.setdefault(pvid, []).append(
            {
                "assessment": a,
                "group": group,
                "patient": patient,
                "css": CLASSIFICATION_CSS.get(score["classification"], "other"),
                "score": score,
            }
        )
    return result
