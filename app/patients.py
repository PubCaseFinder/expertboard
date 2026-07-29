"""Patient and variant data access, plus demo seeding.

For the hackathon each patient row links to on-disk artifacts (a VCF file and a
free-text clinical note) by file path. Variants are parsed out of the VCF and
stored in the ``variants`` table so they can be listed and access-controlled.
"""

import os

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import Session
from app.models import Patient
from app.models import Variant
from app.vcf_import import import_vcf_for_patient


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEMO_PATIENT = {
    "patient_code": "SYN-PATIENT-88291",
    "display_name": "Synthetic HCM proband",
    "diagnosis_name": "Suspected hypertrophic cardiomyopathy (HCM)",
    "vcf_path": "sample-data/synthetic_patient_HCM_variants.vcf",
    "clinical_text_path": "sample-data/synthetic_patient_HCM_clinical.txt",
    "summary": (
        "Entirely synthetic proband with a pre-filtered candidate panel of "
        "cardiomyopathy-related variants for expert board review."
    ),
}


def resolve_path(relative_or_absolute):
    """Resolve a stored path against the project root."""
    if not relative_or_absolute:
        return None
    if os.path.isabs(relative_or_absolute):
        return relative_or_absolute
    return os.path.join(PROJECT_ROOT, relative_or_absolute)


def _ensure_case_patient_id_column(session):
    try:
        session.execute(text("ALTER TABLE cases ADD COLUMN patient_id INT NULL"))
        session.commit()
    except OperationalError:
        session.rollback()


def ensure_demo_patient():
    """Create the demo patient and import its VCF if not already present."""
    session = Session()
    _ensure_case_patient_id_column(session)

    patient = (
        session.query(Patient)
        .filter(Patient.patient_code == DEMO_PATIENT["patient_code"])
        .first()
    )
    if patient is None:
        patient = Patient(
            patient_code=DEMO_PATIENT["patient_code"],
            display_name=DEMO_PATIENT["display_name"],
            diagnosis_name=DEMO_PATIENT["diagnosis_name"],
            vcf_path=DEMO_PATIENT["vcf_path"],
            clinical_text_path=DEMO_PATIENT["clinical_text_path"],
            summary=DEMO_PATIENT["summary"],
        )
        session.add(patient)
        session.flush()

    vcf_full_path = resolve_path(patient.vcf_path)
    already_imported = (
        session.query(Variant).filter(Variant.patient_id == patient.id).count() > 0
    )
    if vcf_full_path and os.path.exists(vcf_full_path) and not already_imported:
        import_vcf_for_patient(session, patient.id, vcf_full_path)

    session.commit()
    return patient


def list_patients():
    session = Session()
    patients = session.query(Patient).order_by(Patient.patient_code).all()
    rows = []
    for patient in patients:
        variant_count = (
            session.query(Variant).filter(Variant.patient_id == patient.id).count()
        )
        rows.append({"patient": patient, "variant_count": variant_count})
    return rows


def get_patient(patient_id):
    session = Session()
    return session.get(Patient, patient_id)


def get_patient_variants(patient_id):
    session = Session()
    return (
        session.query(Variant)
        .filter(Variant.patient_id == patient_id)
        .order_by(Variant.id)
        .all()
    )


def read_clinical_text(patient):
    """Return the free-text clinical note contents, or None if unavailable."""
    if patient is None or not patient.clinical_text_path:
        return None
    full_path = resolve_path(patient.clinical_text_path)
    if not full_path or not os.path.exists(full_path):
        return None
    with open(full_path, "r", encoding="utf-8") as handle:
        return handle.read()
