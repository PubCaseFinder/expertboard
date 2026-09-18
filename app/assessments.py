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
from app.models import PatientPhenotype
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


def parse_evidence(acmg_codes, criterion_comments=None):
    """Convert stored ACMG tokens into individually scored evidence items."""
    valid_codes = {code for code, _label in ACMG_CODES}
    comments = criterion_comments or {}
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
        item = {
            "code": code,
            "strength": strength,
            "points": points,
        }
        comment = str(comments.get(code) or "").strip()
        if comment:
            item["comment"] = comment
        evidence.append(item)
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
    criterion_comments=None,
    annotation_snapshot=None,
):
    """Create an assessment. Returns (assessment, error)."""
    evidence = parse_evidence(acmg_codes, criterion_comments)
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
        criterion_comments=json.dumps(
            criterion_comments or {}, ensure_ascii=False, separators=(",", ":")
        ),
        annotation_snapshot=(annotation_snapshot or "").strip() or None,
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


def _va_spec_direction(classification):
    if classification in ("Pathogenic", "Likely pathogenic"):
        return "supports"
    if classification in ("Benign", "Likely benign"):
        return "disputes"
    return "neutral"


def _va_spec_evidence_outcome(evidence_item):
    if evidence_item["points"] > 0:
        return "supports"
    if evidence_item["points"] < 0:
        return "disputes"
    return "neutral"


def _saved_variant_annotations(variant):
    """Extract displayable VEP/VCF annotations from the persisted INFO string."""
    annotation_keys = (
        "GENE", "HGVSC", "HGVSP", "CLNSIG", "REVEL", "CADD_PHRED",
        "gnomAD_AF", "gnomAD_AF_POPMAX", "LOEUF", "pLI",
        "SpliceAI_AG", "SpliceAI_AL", "SpliceAI_DG", "SpliceAI_DL", "NOTE",
    )
    raw_values = {}
    for item in (variant.raw_info or "").split(";"):
        key, separator, value = item.partition("=")
        if separator and key in annotation_keys and value not in ("", "."):
            raw_values[key] = value
    return [{"name": key, "value": value} for key, value in raw_values.items()]


def _assessment_variant_annotations(assessment, variant, patient=None):
    """Prefer the annotation snapshot a curator viewed over imported VCF INFO."""
    try:
        snapshot = json.loads(assessment.annotation_snapshot or "")
    except (TypeError, ValueError):
        snapshot = None
    if not isinstance(snapshot, dict) or not snapshot:
        annotations = _saved_variant_annotations(variant)
        source = "Imported VCF INFO"
    else:
        annotations = [{"name": "Annotation source", "value": "Refreshed VEP / VRS snapshot"}]
        if snapshot.get("vep"):
            annotations.append({
                "name": "Ensembl VEP response",
                "value": json.dumps(snapshot["vep"], ensure_ascii=False, indent=2),
            })
        if snapshot.get("vrs"):
            annotations.append({
                "name": "GA4GH VRS response",
                "value": json.dumps(snapshot["vrs"], ensure_ascii=False, indent=2),
            })
        source = "Refreshed VEP / VRS snapshot"

    context = snapshot.get("confirmed_clinical_context") if isinstance(snapshot, dict) else None
    if not context and patient is not None:
        context = _patient_clinical_context_annotation(patient)
    if context and (context.get("ancestry") or context.get("diseases")):
        annotations.append({
            "name": "Confirmed clinical context",
            "value": json.dumps(context, ensure_ascii=False, indent=2),
        })
        source += " + confirmed clinical context"
    evidence_basis = _assessment_evidence_basis_annotation(assessment)
    if evidence_basis:
        annotations.append({
            "name": "AI evidence basis",
            "value": json.dumps(evidence_basis["value"], ensure_ascii=False, indent=2),
        })
    return annotations, source


def _assessment_pubcasefinder_annotation(assessment):
    """Return PubCaseFinder context saved when the curator requested it."""
    try:
        snapshot = json.loads(assessment.annotation_snapshot or "")
    except (TypeError, ValueError):
        snapshot = None
    if not isinstance(snapshot, dict) or not snapshot.get("pubcasefinder"):
        return None
    return {
        "name": "expertboardPubCaseFinderAnnotation",
        "value": snapshot["pubcasefinder"],
    }


def _assessment_evidence_basis_annotation(assessment):
    """Return AI's per-criterion source/value explanations saved at assessment time."""
    try:
        snapshot = json.loads(assessment.annotation_snapshot or "")
    except (TypeError, ValueError):
        snapshot = None
    if not isinstance(snapshot, dict) or not snapshot.get("evidence_basis"):
        return None
    return {
        "name": "expertboardAIEvidenceBasis",
        "value": snapshot["evidence_basis"],
    }


def _patient_clinical_context_annotation(patient):
    from app import patients as patients_module

    context = patients_module.get_clinical_context(patient)
    return context or None


def _va_spec_document(assessment, variant, patient, summary):
    """Build the reviewable VA-Spec representation from saved assessment data."""
    classification = summary["classification"]
    annotations, annotation_source = _assessment_variant_annotations(assessment, variant, patient)
    pubcasefinder_annotation = _assessment_pubcasefinder_annotation(assessment)
    evidence_basis_annotation = _assessment_evidence_basis_annotation(assessment)
    clinical_context = _patient_clinical_context_annotation(patient)
    proposition = {
        "id": f"urn:expertboard:proposition:variant-{variant.id}",
        "type": "VariantPathogenicityProposition",
        "subjectVariant": f"urn:expertboard:variant:{variant.id}",
        "predicate": "isCausalFor",
        "objectCondition": {
            "id": f"urn:expertboard:patient:{patient.id}:condition",
            "conceptType": "Disease",
            "name": patient.diagnosis_name or "Unspecified condition",
        },
    }
    if variant.gene:
        proposition["geneContextQualifier"] = {
            "conceptType": "Gene",
            "name": variant.gene,
        }

    extensions = [
        {"name": "tavtigianTotalScore", "value": summary["total_score"]},
        {
            "name": "posteriorProbability",
            "value": summary["posterior_probability"],
        },
        {
            "name": "reviewerLbThresholdOverride",
            "value": summary["reviewer_override"],
        },
    ]
    if assessment.notes:
        extensions.append({"name": "reviewerNotes", "value": assessment.notes})

    return {
        "id": f"urn:expertboard:assessment:{assessment.id}",
        "type": "Statement",
        "proposition": proposition,
        "direction": _va_spec_direction(classification),
        "classification": {
            "primaryCoding": {
                "code": classification.lower(),
                "system": "ACMG Guidelines, 2015",
            },
            "name": classification,
        },
        "contributions": [{
            "type": "Contribution",
            "contributor": {
                "type": "Agent",
                "name": assessment.assessed_by or "Unknown reviewer",
            },
            "activityType": "evidence evaluation",
            "date": str(assessment.created_at)[:10],
        }],
        "specifiedBy": {
            "type": "Method",
            "name": "ACMG Guidelines, 2015",
            "methodType": "guideline",
            "reportedIn": {
                "type": "Document",
                "pmid": "25741868",
                "name": "Richards et al., 2015, Genet Med.",
            },
        },
        "hasEvidenceLines": [{
            "type": "EvidenceLine",
            "direction": _va_spec_evidence_outcome(item),
            "evidence": {
                "type": "Evidence",
                "name": item["code"],
                "strength": item["strength"],
                "comment": item.get("comment"),
                "extensions": ([{
                    "name": "expertboardSavedVcfAnnotation",
                    "value": annotations,
                }, {
                    "name": "expertboardAnnotationSource",
                    "value": annotation_source,
                    }] + ([pubcasefinder_annotation] if pubcasefinder_annotation else [])
                    + ([evidence_basis_annotation] if evidence_basis_annotation else [])
                     + ([{"name": "expertboardConfirmedClinicalContext", "value": clinical_context}]
                         if clinical_context else [])),
            },
        } for item in summary["evidence"]],
        "extensions": extensions,
    }


def list_va_spec_review_records():
    """Return all saved assessments as VA-Spec documents for implementation review."""
    session = Session()
    rows = (
        session.query(VariantAssessment, Variant, Patient)
        .join(Variant, Variant.id == VariantAssessment.variant_id)
        .join(Patient, Patient.id == Variant.patient_id)
        .order_by(asc(Variant.gene), asc(Patient.patient_code), asc(VariantAssessment.id))
        .all()
    )
    patient_ids = {patient.id for _assessment, _variant, patient in rows}
    phenotypes_by_patient = {}
    if patient_ids:
        phenotype_rows = (
            session.query(PatientPhenotype)
            .filter(PatientPhenotype.patient_id.in_(patient_ids))
            .order_by(asc(PatientPhenotype.hpo_id))
            .all()
        )
        for phenotype in phenotype_rows:
            phenotypes_by_patient.setdefault(phenotype.patient_id, []).append(phenotype)

    result = []
    for assessment, variant, patient in rows:
        summary = assessment_summary(assessment)
        annotations, annotation_source = _assessment_variant_annotations(assessment, variant, patient)
        document = _va_spec_document(assessment, variant, patient, summary)
        result.append({
            "assessment": assessment,
            "variant": variant,
            "patient": patient,
            "summary": summary,
            "document": document,
            "document_json": json.dumps(document, ensure_ascii=False, indent=2),
            "patient_phenotypes": phenotypes_by_patient.get(patient.id, []),
            "variant_annotations": annotations,
            "annotation_source": annotation_source,
        })

    assessments_by_variant = {}
    for record in result:
        assessments_by_variant.setdefault(record["variant"].id, []).append(record)
    for record in result:
        record["related_assessments"] = assessments_by_variant[record["variant"].id]
    return result


def group_va_spec_records_by_gene_position(records):
    """Group review records by gene and full GRCh38 variant allele."""
    by_gene = {}
    for record in records:
        variant = record["variant"]
        gene = variant.gene or "No gene assigned"
        variant_key = (variant.chrom, variant.pos, variant.ref, variant.alt)
        group = by_gene.setdefault(gene, {}).setdefault(variant_key, {
            "chrom": variant.chrom,
            "pos": variant.pos,
            "ref": variant.ref,
            "alt": variant.alt,
            "records": [],
            "patients": {},
            "hpo_terms": {},
            "classification_counts": {},
            "diagnosis_counts": {},
        })
        group["records"].append(record)
        classification = record["summary"]["classification"]
        group["classification_counts"][classification] = (
            group["classification_counts"].get(classification, 0) + 1
        )
        patient = record["patient"]
        if patient.id not in group["patients"]:
            group["patients"][patient.id] = patient
            diagnosis = patient.diagnosis_name or "Unspecified condition"
            group["diagnosis_counts"][diagnosis] = (
                group["diagnosis_counts"].get(diagnosis, 0) + 1
            )
            for phenotype in record["patient_phenotypes"]:
                term = group["hpo_terms"].setdefault(phenotype.hpo_id, {
                    "id": phenotype.hpo_id,
                    "label": phenotype.hpo_label or "-",
                    "count": 0,
                })
                term["count"] += 1

    grouped = {}
    for gene, positions in by_gene.items():
        groups = []
        for group in positions.values():
            group["patients"] = sorted(
                group["patients"].values(), key=lambda patient: patient.patient_code
            )
            group["hpo_terms"] = sorted(
                group["hpo_terms"].values(),
                key=lambda term: (-term["count"], term["id"]),
            )
            group["classification_counts"] = sorted(
                group["classification_counts"].items(), key=lambda item: item[0]
            )
            group["diagnosis_counts"] = sorted(
                group["diagnosis_counts"].items(), key=lambda item: (-item[1], item[0])
            )
            groups.append(group)
        grouped[gene] = sorted(
            groups, key=lambda group: (group["chrom"], group["pos"], group["ref"], group["alt"])
        )
    return grouped


def group_va_spec_records_by_classification(records):
    """Group saved review records by their calculated classification."""
    order = {
        "Pathogenic": 0,
        "Likely pathogenic": 1,
        "Uncertain significance": 2,
        "Likely benign": 3,
        "Benign": 4,
    }
    grouped = {}
    for record in records:
        classification = record["summary"].get("classification") or "Unclassified"
        grouped.setdefault(classification, []).append(record)
    return dict(sorted(grouped.items(), key=lambda item: (order.get(item[0], 99), item[0])))


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


def summarize_assessments_for_variants(variants):
    """Summarize all saved assessments for each matching genomic variant."""
    if not variants:
        return {}

    session = Session()
    key_to_variant_id = {
        (variant.chrom, variant.pos, variant.ref, variant.alt): variant.id
        for variant in variants
    }
    chroms = list({variant.chrom for variant in variants})
    matching_variants = (
        session.query(Variant)
        .filter(Variant.chrom.in_(chroms))
        .all()
    )
    matching_ids = {
        variant.id: key_to_variant_id[(variant.chrom, variant.pos, variant.ref, variant.alt)]
        for variant in matching_variants
        if (variant.chrom, variant.pos, variant.ref, variant.alt) in key_to_variant_id
    }
    if not matching_ids:
        return {}

    summaries = {}
    rows = (
        session.query(VariantAssessment)
        .filter(VariantAssessment.variant_id.in_(matching_ids))
        .order_by(asc(VariantAssessment.id))
        .all()
    )
    for assessment in rows:
        variant_id = matching_ids[assessment.variant_id]
        summary = summaries.setdefault(variant_id, {
            "assessment_count": 0,
            "classification_counts": {},
            "code_counts": {},
        })
        summary["assessment_count"] += 1
        classification = assessment_summary(assessment)["classification"]
        summary["classification_counts"][classification] = (
            summary["classification_counts"].get(classification, 0) + 1
        )
        for evidence in assessment_summary(assessment)["evidence"]:
            code = evidence["code"]
            summary["code_counts"][code] = summary["code_counts"].get(code, 0) + 1

    for summary in summaries.values():
        summary["classifications"] = sorted(summary.pop("classification_counts").items())
        summary["codes"] = sorted(summary.pop("code_counts").items())
    return summaries
