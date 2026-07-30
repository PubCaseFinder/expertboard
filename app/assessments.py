"""Variant assessment CRUD.

Each assessment records one expert group's classification of a single variant.
Different groups (e.g. Japan Rare Disease Panel, Singapore Medical Genetics)
may hold different classifications for the same variant, enabling side-by-side
country/group comparison on the patient detail page.
"""

from sqlalchemy import asc

from app.db import Session
from app.models import ExpertGroup
from app.models import VariantAssessment


CLASSIFICATIONS = [
    ("Pathogenic",            "Pathogenic"),
    ("Likely pathogenic",     "Likely pathogenic"),
    ("Uncertain significance","Uncertain significance (VUS)"),
    ("Likely benign",         "Likely benign"),
    ("Benign",                "Benign"),
    ("Drug response",         "Drug response"),
    ("Risk factor",           "Risk factor"),
    ("Protective",            "Protective"),
    ("Other",                 "Other"),
]

EVIDENCE_LEVELS = [
    ("",            "—"),
    ("strong",      "Strong"),
    ("moderate",    "Moderate"),
    ("supporting",  "Supporting"),
]

# CSS suffix used in template: assess-<key>
CLASSIFICATION_CSS = {
    "Pathogenic":             "p",
    "Likely pathogenic":      "lp",
    "Uncertain significance": "vus",
    "Likely benign":          "lb",
    "Benign":                 "b",
    "Drug response":          "dr",
    "Risk factor":            "rf",
    "Protective":             "prot",
    "Other":                  "other",
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
        group = session.get(ExpertGroup, a.expert_group_id) if a.expert_group_id else None
        result.setdefault(a.variant_id, []).append(
            {
                "assessment": a,
                "group": group,
                "css": CLASSIFICATION_CSS.get(a.classification, "other"),
            }
        )
    return result


def add_assessment(variant_id, expert_group_id, classification, evidence_level, notes, assessed_by):
    """Create an assessment. Returns (assessment, error)."""
    classification = (classification or "").strip()
    valid = {k for k, _ in CLASSIFICATIONS}
    if classification not in valid:
        return None, "Please choose a valid classification."

    raw_gid = str(expert_group_id or "").strip()
    gid = int(raw_gid) if raw_gid.isdigit() else None

    session = Session()
    if gid:
        if session.get(ExpertGroup, gid) is None:
            return None, "Expert group not found."

    a = VariantAssessment(
        variant_id=int(variant_id),
        expert_group_id=gid,
        classification=classification,
        evidence_level=(evidence_level or "").strip() or None,
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
