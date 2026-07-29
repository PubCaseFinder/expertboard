"""Patient and variant data access, plus VCF upload import.

Each patient row links to its uploaded VCF file by path. Variants are parsed out
of the VCF and stored in the ``variants`` table so they can be listed per patient.
"""

import os

from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import Session
from app.models import Patient
from app.models import Variant
from app.vcf_import import import_variants_for_patient
from app.vcf_import import parse_vcf_records


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")

ALLOWED_EXTENSIONS = (".vcf", ".txt")

# Review lifecycle a patient moves through. Expert panels / reviews are
# organized based on the patient's current status.
DEFAULT_REVIEW_STATUS = "pending_review"

REVIEW_STATUSES = [
    "pending_review",
    "board_validation",
    "panel_scheduled",
    "review_complete",
]

REVIEW_STATUS_LABELS = {
    "pending_review": "Pending review",
    "board_validation": "Validation in progress",
    "panel_scheduled": "Scheduled for expert panel",
    "review_complete": "Review complete",
}

REVIEW_STATUS_HINTS = {
    "pending_review": "Not yet reviewed.",
    "board_validation": "Being validated on the expert board (completes after 5 evaluations).",
    "panel_scheduled": "Scheduled for evaluation at the expert panel.",
    "review_complete": "Review completed.",
}


def review_status_label(status):
    return REVIEW_STATUS_LABELS.get(status, status)


def ensure_schema():
    """Add columns introduced after the patients table was first created."""
    _add_column_if_missing("clinical_text TEXT NULL")
    _add_column_if_missing(
        "review_status VARCHAR(32) NOT NULL DEFAULT 'pending_review'"
    )
    _add_column_if_missing("requested_expert_group_id INT NULL")
    _add_column_if_missing("family_id VARCHAR(64) NULL")
    _add_column_if_missing("family_history TEXT NULL")


def _add_column_if_missing(column_definition):
    session = Session()
    try:
        session.execute(text(f"ALTER TABLE patients ADD COLUMN {column_definition}"))
        session.commit()
    except OperationalError:
        session.rollback()


def resolve_path(relative_or_absolute):
    """Resolve a stored path against the project root."""
    if not relative_or_absolute:
        return None
    if os.path.isabs(relative_or_absolute):
        return relative_or_absolute
    return os.path.join(PROJECT_ROOT, relative_or_absolute)


def is_allowed_filename(filename):
    return bool(filename) and filename.lower().endswith(ALLOWED_EXTENSIONS)


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


def list_patients_by_status():
    """Group patients into review-lifecycle buckets for the review queue.

    Returns a list of columns in lifecycle order, each with its label, hint,
    and the patient rows currently in that status.
    """
    rows = list_patients()
    buckets = {status: [] for status in REVIEW_STATUSES}
    for row in rows:
        status = row["patient"].review_status
        buckets.setdefault(status, []).append(row)
    return [
        {
            "status": status,
            "label": REVIEW_STATUS_LABELS.get(status, status),
            "hint": REVIEW_STATUS_HINTS.get(status, ""),
            "rows": buckets.get(status, []),
        }
        for status in REVIEW_STATUSES
    ]


def get_patient(patient_id):
    session = Session()
    return session.get(Patient, patient_id)


def list_family_members(patient_id):
    """Return other patients that share this patient's family (kindred) ID."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None or not patient.family_id:
        return []
    return (
        session.query(Patient)
        .filter(Patient.family_id == patient.family_id)
        .filter(Patient.id != patient.id)
        .order_by(Patient.patient_code)
        .all()
    )


def save_family_info(patient_id, family_id, family_history):
    """Update the patient's kindred ID and free-text family history. Returns the patient."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.family_id = (family_id or "").strip() or None
    patient.family_history = (family_history or "").strip() or None
    session.commit()
    return patient


def save_clinical_text(patient_id, clinical_text):
    """Store the patient's free-text clinical description. Returns the patient."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.clinical_text = clinical_text or None
    session.commit()
    return patient


def set_review_status(patient_id, status):
    """Update the patient's review lifecycle status. Returns the patient."""
    if status not in REVIEW_STATUSES:
        return None
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.review_status = status
    session.commit()
    return patient


def set_requested_expert_group(patient_id, expert_group_id):
    """Assign (or clear) the expert group a patient is referred to. Returns the patient."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.requested_expert_group_id = expert_group_id or None
    session.commit()
    return patient


def get_patient_variants(patient_id):
    session = Session()
    return (
        session.query(Variant)
        .filter(Variant.patient_id == patient_id)
        .order_by(Variant.id)
        .all()
    )


def _get_or_create_patient(session, patient_code, display_name, diagnosis_name, vcf_path):
    patient = (
        session.query(Patient).filter(Patient.patient_code == patient_code).first()
    )
    if patient is None:
        patient = Patient(patient_code=patient_code)
        session.add(patient)
    patient.display_name = display_name or patient.display_name
    patient.diagnosis_name = diagnosis_name or patient.diagnosis_name
    patient.vcf_path = vcf_path
    session.flush()
    return patient


def _store_uploaded_file(patient_code, file_storage, content):
    """Persist the uploaded VCF under ``uploads/`` and return its relative path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = secure_filename(file_storage.filename or "upload.vcf")
    safe_code = secure_filename(patient_code) or "patient"
    stored_name = f"{safe_code}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(stored_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return os.path.relpath(stored_path, PROJECT_ROOT)


def import_uploaded_vcf(file_storage, patient_code, display_name, diagnosis_name):
    """Parse an uploaded VCF, store the file, and replace the patient's variants.

    Returns ``(patient, variant_count)``.
    """
    raw = file_storage.read()
    content = raw.decode("utf-8", errors="replace")
    lines = content.splitlines()

    stored_path = _store_uploaded_file(patient_code, file_storage, content)

    session = Session()
    patient = _get_or_create_patient(
        session, patient_code, display_name, diagnosis_name, stored_path
    )
    count = import_variants_for_patient(
        session, patient.id, parse_vcf_records(lines)
    )
    session.commit()
    return patient, count

