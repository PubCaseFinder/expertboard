"""Variant assessment CRUD.

Each assessment records one expert group's classification of a single variant.
Different groups (e.g. Japan Rare Disease Panel, Singapore Medical Genetics)
may hold different classifications for the same variant, enabling side-by-side
country/group comparison on the patient detail page.
"""

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

ACMG_CODES = [
    # Pathogenic criteria
    ("PVS1", "PVS1 (Very strong: Null variant)"),
    ("PS1",  "PS1 (Strong: Same amino acid change)"),
    ("PS2",  "PS2 (Strong: De novo confirmed)"),
    ("PS3",  "PS3 (Strong: Functional study)"),
    ("PS4",  "PS4 (Strong: Prevalence in affected)"),
    ("PM1",  "PM1 (Moderate: Mutational hot spot)"),
    ("PM2",  "PM2 (Moderate: Absent/low in control DB)"),
    ("PM3",  "PM3 (Moderate: In trans with pathogenic)"),
    ("PM4",  "PM4 (Moderate: Protein length change)"),
    ("PM5",  "PM5 (Moderate: Novel missense at same AA)"),
    ("PM6",  "PM6 (Moderate: De novo assumed)"),
    ("PP1",  "PP1 (Supporting: Co-segregation)"),
    ("PP2",  "PP2 (Supporting: Missense in constrained gene)"),
    ("PP3",  "PP3 (Supporting: Multiple computational evidence)"),
    ("PP4",  "PP4 (Supporting: Specific phenotype fit)"),
    ("PP5",  "PP5 (Supporting: Reputable source)"),
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
    ("BP6",  "BP6 (Supporting: Reputable source benign)"),
    ("BP7",  "BP7 (Supporting: Silent/synonymous no splice effect)"),
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
        group = session.get(ExpertBoard, a.expert_board_id) if a.expert_board_id else None
        result.setdefault(a.variant_id, []).append(
            {
                "assessment": a,
                "group": group,
                "css": CLASSIFICATION_CSS.get(a.classification, "other"),
            }
        )
    return result


def add_assessment(variant_id, expert_board_id, classification, evidence_level, notes, assessed_by, acmg_codes=None):
    """Create an assessment. Returns (assessment, error)."""
    classification = (classification or "").strip()
    valid = {k for k, _ in CLASSIFICATIONS}
    if classification not in valid:
        return None, "Please choose a valid classification."

    raw_gid = str(expert_board_id or "").strip()
    gid = int(raw_gid) if raw_gid.isdigit() else None

    session = Session()
    if gid:
        if session.get(ExpertBoard, gid) is None:
            return None, "Expert board not found."

    a = VariantAssessment(
        variant_id=int(variant_id),
        expert_board_id=gid,
        classification=classification,
        evidence_level=(evidence_level or "").strip() or None,
        acmg_codes=(acmg_codes or "").strip() or None,
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
        result.setdefault(pvid, []).append(
            {
                "assessment": a,
                "group": group,
                "patient": patient,
                "css": CLASSIFICATION_CSS.get(a.classification, "other"),
            }
        )
    return result
