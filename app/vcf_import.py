"""Minimal VCF parser and importer.

Parses a VCFv4.x file, extracts per-variant annotation from the INFO and
FORMAT/sample columns, and stores one row per variant in the ``variants`` table.

The parser is intentionally small and dependency-free: it understands the
standard 8 fixed columns (CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO) plus an
optional FORMAT column and a single sample column.
"""

import re
from urllib.parse import unquote

from app.models import Variant
from app.models import VariantAssessment


CSQ_FORMAT_RE = re.compile(r"Format:\s*([^\"]+)")


def _classify_variant_type(ref, alt):
    if not ref or not alt:
        return "unknown"
    if "," in alt:
        alt = alt.split(",", 1)[0]
    if len(ref) == 1 and len(alt) == 1:
        return "SNV"
    if len(ref) < len(alt):
        return "insertion"
    if len(ref) > len(alt):
        return "deletion"
    return "MNV"


def _parse_info(info_field):
    """Turn ``KEY=VALUE;FLAG;...`` into a dict."""
    info = {}
    if not info_field or info_field == ".":
        return info
    for chunk in info_field.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            info[key.strip()] = value.strip()
        else:
            info[chunk] = True
    return info


def _parse_sample(format_field, sample_field):
    """Zip the FORMAT keys with the sample values (e.g. GT:DP:GQ)."""
    if not format_field or not sample_field:
        return {}
    keys = format_field.split(":")
    values = sample_field.split(":")
    return dict(zip(keys, values))


def _parse_csq_fields(header_line):
    """Return the ordered field names from a VEP CSQ INFO header."""
    if "ID=CSQ" not in header_line and "ID=VEP_CSQ" not in header_line:
        return None
    match = CSQ_FORMAT_RE.search(header_line)
    if not match:
        return None
    return [field.strip().rstrip(">") for field in match.group(1).split("|")]


def _mane_annotation(info, csq_fields):
    """Select the MANE transcript from VEP CSQ annotations."""
    csq_value = info.get("CSQ") or info.get("VEP_CSQ")
    if not csq_fields or not csq_value:
        return {}

    annotations = []
    for value in str(csq_value).split(","):
        fields = value.split("|")
        annotations.append(dict(zip(csq_fields, fields)))

    for mane_key in ("MANE_SELECT", "MANE_PLUS_CLINICAL"):
        for annotation in annotations:
            if annotation.get(mane_key):
                return annotation
    return {}


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_vcf_records(lines):
    """Yield a dict of parsed fields for every variant record.

    ``lines`` is any iterable of text lines (e.g. an open file handle or a list
    produced from an uploaded file), so the same parser works for on-disk files
    and browser uploads.
    """
    csq_fields = None
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line:
            continue
        if line.startswith("##"):
            parsed_fields = _parse_csq_fields(line)
            if parsed_fields:
                csq_fields = parsed_fields
            continue
        if line.startswith("#"):
            continue

        columns = line.split("\t")
        if len(columns) < 8:
            continue

        chrom, pos, ext_id, ref, alt, qual, filt, info_field = columns[:8]
        format_field = columns[8] if len(columns) > 8 else ""
        sample_field = columns[9] if len(columns) > 9 else ""

        info = _parse_info(info_field)
        sample = _parse_sample(format_field, sample_field)
        mane = _mane_annotation(info, csq_fields)

        yield {
            "chrom": chrom,
            "pos": _to_int(pos) or 0,
            "variant_ext_id": info.get("RSID") or (None if ext_id == "." else ext_id),
            "ref": ref,
            "alt": alt,
            "gene": mane.get("SYMBOL") or info.get("GENE"),
            "hgvs_c": unquote(
                info.get("MANE_HGVSC")
                or mane.get("HGVSc")
                or info.get("VEP_HGVSC")
                or info.get("HGVSC")
                or ""
            ) or None,
            "hgvs_p": unquote(
                info.get("MANE_HGVSP")
                or mane.get("HGVSp")
                or info.get("VEP_HGVSP")
                or info.get("HGVSP")
                or ""
            ) or None,
            "variant_type": _classify_variant_type(ref, alt),
            "clin_sig": info.get("CLNSIG"),
            "note": info.get("NOTE"),
            "genotype": sample.get("GT"),
            "depth": _to_int(sample.get("DP")),
            "genotype_quality": _to_int(sample.get("GQ")),
            "quality": None if qual == "." else qual,
            "filter_status": None if filt == "." else filt,
            "raw_info": info_field,
        }


def parse_vcf(path):
    """Yield parsed variant records from a VCF file on disk."""
    with open(path, "r", encoding="utf-8") as handle:
        yield from parse_vcf_records(handle)


def import_variants_for_patient(session, patient_id, records):
    """Replace the variant rows for ``patient_id`` with ``records``.

    Existing rows with the same chromosome, position, REF, and ALT are updated
    in place so their assessments remain attached.

    Returns the number of variants imported.
    """
    existing = session.query(Variant).filter(Variant.patient_id == patient_id).all()
    existing_by_key = {
        (variant.chrom, variant.pos, variant.ref, variant.alt): variant
        for variant in existing
    }
    retained_ids = set()

    count = 0
    for record in records:
        key = (record["chrom"], record["pos"], record["ref"], record["alt"])
        variant = existing_by_key.get(key)
        if variant is None:
            variant = Variant(patient_id=patient_id)
            session.add(variant)
        else:
            retained_ids.add(variant.id)
        for field, value in record.items():
            setattr(variant, field, value)
        count += 1

    stale_ids = [variant.id for variant in existing if variant.id not in retained_ids]
    if stale_ids:
        session.query(VariantAssessment).filter(
            VariantAssessment.variant_id.in_(stale_ids)
        ).delete(synchronize_session=False)
        session.query(Variant).filter(Variant.id.in_(stale_ids)).delete(
            synchronize_session=False
        )

    session.flush()
    return count


def import_vcf_for_patient(session, patient_id, path):
    """Replace the variant rows for ``patient_id`` with the contents of ``path``.

    Returns the number of variants imported.
    """
    return import_variants_for_patient(session, patient_id, parse_vcf(path))
