"""Patient and variant data access, plus VCF upload import.

Each patient row links to its uploaded VCF file by path. Variants are parsed out
of the VCF and stored in the ``variants`` table so they can be listed per patient.
"""

import json
import os
from datetime import datetime

from werkzeug.utils import secure_filename
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import Session
from app.models import Patient
from app.models import PatientPhenotype
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
    _add_column_if_missing("clinical_context LONGTEXT NULL")
    _add_column_if_missing(
        "review_status VARCHAR(32) NOT NULL DEFAULT 'pending_review'"
    )
    _add_column_if_missing("requested_expert_board_id INT NULL")
    _add_column_if_missing("family_id VARCHAR(64) NULL")
    _add_column_if_missing("family_history TEXT NULL")
    _add_column_if_missing("vep_annotation LONGTEXT NULL", table_name="variants")
    _add_column_if_missing(
        "vep_annotation_updated_at TIMESTAMP NULL", table_name="variants"
    )
    _add_column_if_missing("clinvar_annotation LONGTEXT NULL", table_name="variants")
    _add_column_if_missing(
        "clinvar_annotation_updated_at TIMESTAMP NULL", table_name="variants"
    )


def _add_column_if_missing(column_definition, table_name="patients"):
    session = Session()
    try:
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
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


def save_clinical_context(patient_id, context):
    """Store reviewer-confirmed clinical context with its note provenance."""
    import json

    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.clinical_context = json.dumps(context, ensure_ascii=False)
    session.commit()
    return patient


def get_clinical_context(patient):
    import json

    try:
        context = json.loads(patient.clinical_context or "{}")
    except (TypeError, ValueError):
        context = {}
    return context if isinstance(context, dict) else {}


def list_confirmed_phenotypes(patient_id):
    session = Session()
    return (
        session.query(PatientPhenotype)
        .filter(PatientPhenotype.patient_id == patient_id)
        .order_by(PatientPhenotype.hpo_id)
        .all()
    )


def replace_confirmed_phenotypes(patient_id, phenotype_items, confirmed_by):
    """Synchronize confirmed HPO while preserving existing provenance."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None

    existing = {
        item.hpo_id: item
        for item in session.query(PatientPhenotype)
        .filter(PatientPhenotype.patient_id == patient_id)
        .all()
    }
    requested_ids = {item["hpo_id"] for item in phenotype_items}
    for hpo_id, record in existing.items():
        if hpo_id not in requested_ids:
            session.delete(record)
    for item in phenotype_items:
        if item["hpo_id"] in existing:
            continue
        session.add(
            PatientPhenotype(
                patient_id=patient_id,
                hpo_id=item["hpo_id"],
                hpo_label=item.get("label") or None,
                source=item.get("source") or "clinical_text_review",
                source_quote=item.get("source_text") or None,
                confirmed_by=confirmed_by,
            )
        )
    session.commit()
    return list_confirmed_phenotypes(patient_id)


def remove_confirmed_phenotype(patient_id, hpo_id):
    session = Session()
    deleted = (
        session.query(PatientPhenotype)
        .filter(PatientPhenotype.patient_id == patient_id)
        .filter(PatientPhenotype.hpo_id == hpo_id)
        .delete()
    )
    session.commit()
    return bool(deleted)


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


def set_requested_expert_group(patient_id, expert_board_id):
    """Assign (or clear) the expert board a patient is referred to. Returns the patient."""
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        return None
    patient.requested_expert_board_id = expert_board_id or None
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


def save_vep_annotation(patient_id, variant_id, annotation):
    """Persist the latest successful VEP/VRS annotation for a patient variant."""
    session = Session()
    variant = session.get(Variant, variant_id)
    if variant is None or variant.patient_id != patient_id:
        return None
    variant.vep_annotation = json.dumps(annotation, ensure_ascii=False)
    variant.vep_annotation_updated_at = datetime.utcnow()
    session.commit()
    return variant


def save_clinvar_annotation(patient_id, variant_id, annotation):
    """Persist the latest ClinVar query result for a patient variant."""
    session = Session()
    variant = session.get(Variant, variant_id)
    if variant is None or variant.patient_id != patient_id:
        return None
    variant.clinvar_annotation = json.dumps(annotation, ensure_ascii=False)
    variant.clinvar_annotation_updated_at = datetime.utcnow()
    session.commit()
    return variant


def save_llm_scores(patient_id, result):
    """Persist LLM analysis reasoning to variant rows.

    ``result`` is a dict: {variant_id (int or str): {score, patient_symptoms, gene_diseases, ...}}
    """
    session = Session()
    for vid_key, info in result.items():
        vid = int(vid_key)
        v = session.get(Variant, vid)
        if v is None or v.patient_id != patient_id:
            continue
        v.llm_score = info.get("score")
        # Store full reasoning as JSON string
        import json as _json
        v.llm_reason = _json.dumps({
            "patient_symptoms": info.get("patient_symptoms", ""),
            "gene_diseases": info.get("gene_diseases", ""),
            "relevance": info.get("relevance", ""),
            "population_frequency": info.get("population_frequency", ""),
            "in_silico_predictions": info.get("in_silico_predictions", ""),
            "family_history": info.get("family_history", ""),
            "score_rationale": info.get("score_rationale", ""),
            "suggested_acmg": info.get("suggested_acmg", []),
            "evidence_basis": info.get("evidence_basis", []),
            "missing_data": info.get("missing_data", []),
        }, ensure_ascii=False)
    session.commit()


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


def import_vcf_for_existing_patient(patient_id, file_storage):
    """Replace variants for an already-registered patient from an uploaded VCF.

    Returns ``(patient, variant_count)`` or raises ValueError if patient not found.
    """
    session = Session()
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found")

    raw = file_storage.read()
    content = raw.decode("utf-8", errors="replace")
    lines = content.splitlines()

    stored_path = _store_uploaded_file(patient.patient_code, file_storage, content)
    patient.vcf_path = stored_path

    count = import_variants_for_patient(session, patient.id, parse_vcf_records(lines))
    session.commit()
    return patient, count

