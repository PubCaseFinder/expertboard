"""Structured family member (pedigree) data access.

Each FamilyMember row belongs to one proband (patient_id). If the relative is
also registered as a patient, linked_patient_id links to their record so variant
data can be accessed directly.
"""

from sqlalchemy import asc

from app.db import Session
from app.models import FamilyMember
from app.models import Patient


RELATIONSHIPS = [
    ("mother",               "Mother"),
    ("father",               "Father"),
    ("child",                "Child"),
    ("sibling",              "Sibling"),
    ("half_sibling",         "Half-sibling"),
    ("maternal_grandmother", "Maternal grandmother"),
    ("maternal_grandfather", "Maternal grandfather"),
    ("paternal_grandmother", "Paternal grandmother"),
    ("paternal_grandfather", "Paternal grandfather"),
    ("maternal_uncle_aunt",  "Maternal uncle/aunt"),
    ("paternal_uncle_aunt",  "Paternal uncle/aunt"),
    ("cousin",               "Cousin"),
    ("other",                "Other"),
]

RELATIONSHIP_LABELS = {k: v for k, v in RELATIONSHIPS}

AFFECTED_OPTIONS = [
    ("unknown",    "Unknown"),
    ("affected",   "Affected"),
    ("unaffected", "Unaffected"),
    ("deceased",   "Deceased"),
]


def list_family_members(patient_id):
    """Return all family member rows for a proband, with linked patient objects."""
    session = Session()
    rows = (
        session.query(FamilyMember)
        .filter(FamilyMember.patient_id == patient_id)
        .order_by(asc(FamilyMember.id))
        .all()
    )
    result = []
    for member in rows:
        linked = (
            session.get(Patient, member.linked_patient_id)
            if member.linked_patient_id
            else None
        )
        result.append(
            {
                "member": member,
                "relationship_label": RELATIONSHIP_LABELS.get(
                    member.relationship, member.relationship
                ),
                "linked_patient": linked,
            }
        )
    return result


def list_patients_for_linking():
    """Return all patients as (id, label) for the linked-patient select."""
    session = Session()
    patients = session.query(Patient).order_by(asc(Patient.patient_code)).all()
    return [
        {
            "id": p.id,
            "label": f"{p.patient_code}"
            + (f" — {p.display_name}" if p.display_name else ""),
        }
        for p in patients
    ]


def add_family_member(
    patient_id, relationship, display_name, affected, medical_history, linked_patient_id
):
    """Add a structured family member to a patient. Returns (member, error)."""
    relationship = (relationship or "").strip()
    display_name = (display_name or "").strip() or None
    affected = (affected or "unknown").strip()
    medical_history = (medical_history or "").strip() or None

    if relationship not in RELATIONSHIP_LABELS:
        return None, "Please choose a valid relationship."

    raw_linked = str(linked_patient_id or "").strip()
    linked_id = int(raw_linked) if raw_linked.isdigit() else None

    session = Session()
    if linked_id:
        linked_patient = session.get(Patient, linked_id)
        if linked_patient is None:
            return None, "Linked patient not found."
        # Auto-fill name from linked patient if not given
        if not display_name:
            display_name = linked_patient.display_name or linked_patient.patient_code

    member = FamilyMember(
        patient_id=patient_id,
        relationship=relationship,
        display_name=display_name,
        affected=affected,
        medical_history=medical_history,
        linked_patient_id=linked_id,
    )
    session.add(member)
    session.commit()
    return member, None


def remove_family_member(patient_id, member_id):
    """Remove a family member row. Returns True if removed."""
    session = Session()
    member = session.get(FamilyMember, member_id)
    if member is None or member.patient_id != patient_id:
        return False
    session.delete(member)
    session.commit()
    return True
