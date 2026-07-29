"""Minimal VCF parser and importer.

Parses a VCFv4.x file, extracts per-variant annotation from the INFO and
FORMAT/sample columns, and stores one row per variant in the ``variants`` table.

The parser is intentionally small and dependency-free: it understands the
standard 8 fixed columns (CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO) plus an
optional FORMAT column and a single sample column.
"""

from app.models import Variant


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


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_vcf(path):
    """Yield a dict of parsed fields for every variant record in the VCF."""
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line or line.startswith("##"):
                continue
            if line.startswith("#CHROM") or line.startswith("#"):
                continue

            columns = line.split("\t")
            if len(columns) < 8:
                continue

            chrom, pos, ext_id, ref, alt, qual, filt, info_field = columns[:8]
            format_field = columns[8] if len(columns) > 8 else ""
            sample_field = columns[9] if len(columns) > 9 else ""

            info = _parse_info(info_field)
            sample = _parse_sample(format_field, sample_field)

            yield {
                "chrom": chrom,
                "pos": _to_int(pos) or 0,
                "variant_ext_id": None if ext_id == "." else ext_id,
                "ref": ref,
                "alt": alt,
                "gene": info.get("GENE"),
                "hgvs_c": info.get("HGVSC"),
                "hgvs_p": info.get("HGVSP"),
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


def import_vcf_for_patient(session, patient_id, path):
    """Replace the variant rows for ``patient_id`` with the contents of ``path``.

    Returns the number of variants imported.
    """
    session.query(Variant).filter(Variant.patient_id == patient_id).delete()

    count = 0
    for record in parse_vcf(path):
        session.add(Variant(patient_id=patient_id, **record))
        count += 1

    session.flush()
    return count
