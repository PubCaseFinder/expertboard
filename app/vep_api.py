"""Ensembl VEP and GA4GH VRS annotation helpers."""

import json
import os
import sys
import time

import requests


VEP_URLS = {
    "GRCH38": "https://rest.ensembl.org/vep/human/region",
    "GRCH37": "https://grch37.rest.ensembl.org/vep/human/region",
}

VEP_OPTIONS = {
    "refseq": 1,
    "hgvs": 1,
    "protein": 1,
    "numbers": 1,
    "mane": 1,
    "CADD": 1,
    "AlphaMissense": 1,
    "SpliceAI": 2,
    "dbNSFP": "REVEL_score",
}


def get_vep_annotations(variants, genome_build="GRCh38"):
    """Fetch VEP annotations using Ensembl's batch region endpoint."""
    build = genome_build.upper()
    if build not in VEP_URLS:
        raise ValueError(f"Unsupported genome build: {genome_build}")

    payload = {"variants": variants, **VEP_OPTIONS}
    retry_statuses = {429, 500, 503}
    response = None
    for attempt in range(1, 4):
        response = requests.post(
            VEP_URLS[build],
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            timeout=45,
        )
        if response.status_code not in retry_statuses or attempt == 3:
            break
        time.sleep(min(int(response.headers.get("Retry-After", "2")), 10))

    response.raise_for_status()
    return response.json()


def get_vrs_allele(chrom, pos, ref, alt, genome_build="GRCh38"):
    """Resolve the sequence, normalize an Allele, and compute its VRS identifier."""
    from ga4gh.core import ga4gh_digest
    from ga4gh.core import ga4gh_identify
    from ga4gh.vrs import models
    from ga4gh.vrs import normalize
    from ga4gh.vrs.dataproxy import create_dataproxy

    data_proxy_uri = os.environ.get(
        "GA4GH_VRS_DATAPROXY_URI",
        "seqrepo+https://services.genomicmedlab.org/seqrepo",
    )
    data_proxy = create_dataproxy(data_proxy_uri)
    sequence_alias = f"{genome_build}:{str(chrom).removeprefix('chr')}"
    refget_accession = data_proxy.derive_refget_accession(sequence_alias)
    if not refget_accession:
        raise ValueError(f"SeqRepo could not resolve {sequence_alias}")

    start = int(pos) - 1
    allele = models.Allele(
        location=models.SequenceLocation(
            sequenceReference=models.SequenceReference(
                refgetAccession=refget_accession
            ),
            start=start,
            end=start + len(ref),
        ),
        state=models.LiteralSequenceExpression(sequence=alt.upper()),
    )
    data_proxy.validate_ref_seq(
        f"ga4gh:{refget_accession}", start, start + len(ref), ref.upper()
    )
    normalized = normalize(allele, data_proxy)
    digest = ga4gh_digest(normalized)
    return {
        "sequence_alias": sequence_alias,
        "sequence_id": f"ga4gh:{refget_accession}",
        "digest": digest,
        "vrs_id": ga4gh_identify(normalized),
        "allele": normalized.model_dump(mode="json", exclude_none=True),
    }


def annotate_variant(chrom, pos, ref, alt, genome_build="GRCh38"):
    """Return VEP and VRS results independently so partial failures remain visible."""
    variant = (
        f"{str(chrom).removeprefix('chr')} {int(pos)} . "
        f"{ref.upper()} {alt.upper()} . . ."
    )
    result = {"input": variant, "genome_build": genome_build}

    try:
        annotations = get_vep_annotations([variant], genome_build)
        result["vep"] = annotations[0] if annotations else None
    except (requests.RequestException, ValueError) as exc:
        result["vep_error"] = str(exc)

    try:
        result["vrs"] = get_vrs_allele(
            chrom, pos, ref, alt, genome_build=genome_build
        )
    except Exception as exc:
        result["vrs_error"] = str(exc)

    return result


def compact_annotation_for_llm(annotation):
    """Keep clinically relevant live fields without sending the full VEP payload."""
    vep = annotation.get("vep") or {}
    transcript_fields = {
        "transcript_id",
        "gene_id",
        "gene_symbol",
        "biotype",
        "impact",
        "consequence_terms",
        "hgvsc",
        "hgvsp",
        "protein_id",
        "mane_select",
        "mane_plus_clinical",
        "cadd_phred",
        "cadd_raw",
        "alphamissense",
        "spliceai",
        "revel_score",
        "sift_prediction",
        "sift_score",
        "polyphen_prediction",
        "polyphen_score",
    }
    transcripts = vep.get("transcript_consequences") or []
    selected = [
        tx for tx in transcripts
        if tx.get("mane_select") or tx.get("mane_plus_clinical")
    ]
    if not selected:
        selected = transcripts[:10]

    colocated = []
    for item in (vep.get("colocated_variants") or [])[:20]:
        colocated.append({
            key: item[key]
            for key in ("id", "allele_string", "clin_sig", "frequencies")
            if key in item
        })

    return {
        "genome_build": annotation.get("genome_build"),
        "vrs": annotation.get("vrs"),
        "vep": {
            key: vep.get(key)
            for key in (
                "input",
                "assembly_name",
                "seq_region_name",
                "start",
                "end",
                "allele_string",
                "most_severe_consequence",
            )
            if vep.get(key) is not None
        },
        "transcript_consequences": [
            {key: tx[key] for key in transcript_fields if key in tx}
            for tx in selected
        ],
        "colocated_variants": colocated,
        "vep_error": annotation.get("vep_error"),
        "vrs_error": annotation.get("vrs_error"),
    }


def get_variant_list(vcf_path):
    """Return Ensembl region strings for all records in a VCF file."""
    variants = []
    with open(vcf_path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            fields = line.rstrip().split("\t")
            variants.append(" ".join(fields[:8]))
    return variants


if __name__ == "__main__":
    annotations = get_vep_annotations(get_variant_list(sys.argv[1]))
    print(json.dumps(annotations, ensure_ascii=False, indent=2))
