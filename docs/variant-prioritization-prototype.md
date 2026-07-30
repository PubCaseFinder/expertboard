# Variant Prioritization Prototype

This document describes the first hackathon prototype for the **Variant Prioritization** component of the Pan-Asian Variant Review Network.

The prototype script was contributed by Francis Tablizo during the hackathon. It parses a VEP-derived TSV file and produces a ranked variant table that can be used as an initial shortlist for expert review.

## Purpose

The goal of this prototype is to support the first step of the workflow:

1. Start from annotated variant calls.
2. Apply simple prioritization rules.
3. Produce a ranked list of candidate variants.
4. Pass the highest-priority variants to the expert evidence review workflow.

This is not intended to replace a full clinical interpretation pipeline. It is a lightweight prototype for demonstrating how variants can be filtered and ranked before expert board review.

## Script Location

```text
scripts/variant_prioritization/vep_parser.py
```

## Usage

```bash
python scripts/variant_prioritization/vep_parser.py <input_tsv>
```

The script writes:

```text
ranked.tsv
```

The output is the input TSV with an additional `Rank` column.

## Required Input Columns

The input file is expected to be a tab-separated VEP output file with at least the following columns.

| Column | Purpose |
|---|---|
| `Transcript_Type` | Used to keep MANE transcript rows |
| `SYMBOL_SOURCE` | Used to keep HGNC gene symbols |
| `HGVSc` | Used to keep rows with transcript-level variant notation |
| `ClinVar_CLNSIG` | ClinVar clinical significance |
| `ClinVar_CLNREVSTAT` | ClinVar review status |
| `ClinVar_CLNSIGCONF` | ClinVar conflicting classification summary |
| `REVEL_score` | In silico missense prediction score |
| `SpliceAI_max` | Maximum SpliceAI score |
| `SG10K_AF` | Singapore population allele frequency |
| `gnomADg_4_AF` | Global gnomAD genome allele frequency |
| `gnomADg_4_AF_eas` | East Asian gnomAD genome allele frequency |
| `gnomADg_4_AF_sas` | South Asian gnomAD genome allele frequency |
| `IMPACT` | VEP impact annotation |

## Ranking Logic

Lower rank numbers indicate higher priority for review.

| Rank | Meaning |
|---:|---|
| 1 | ClinVar pathogenic or likely pathogenic, reviewed by expert panel |
| 2 | ClinVar pathogenic or likely pathogenic, no conflicts |
| 3 | ClinVar pathogenic or likely pathogenic with conflicting classifications, but at least 4 pathogenic or likely pathogenic reports |
| 4 | ClinVar pathogenic or likely pathogenic with conflicting classifications, fewer than 4 pathogenic or likely pathogenic reports |
| 5 | ClinVar uncertain significance |
| 6 | In silico score exceeds threshold, such as REVEL or SpliceAI |
| 7 | Low allele frequency across SG10K and gnomAD frequency columns |
| 8 | VEP `HIGH` impact |
| 9 | VEP `MODERATE` impact |
| 10 | VEP `LOW` impact |
| 100 | Default initial rank before criteria are applied |
| 150 | ClinVar uncertain significance reviewed by expert panel |
| 200 | ClinVar benign or likely benign, no conflicts |
| 300 | ClinVar benign or likely benign, reviewed by expert panel |

## Current Thresholds

| Rule | Prototype threshold |
|---|---:|
| Population allele frequency | `< 0.05` |
| Conflicting ClinVar pathogenic reports | `>= 4` |
| REVEL | `>= 0.5` |
| SpliceAI | `>= 0.20` |

## Role in the Demo Workflow

In the hackathon demo, this script can represent the first prioritization layer:

```text
Annotated VCF / VEP TSV
        |
        v
Variant prioritization prototype
        |
        v
ranked.tsv
        |
        v
Top candidate variants for expert evidence review
```

The next step is to connect the ranked variants to the expert review interface, where reviewers can inspect ACMG/AMP-style evidence candidates and mark each evidence item as accepted, rejected, or pending.

## Limitations

This prototype intentionally keeps the logic simple. Important limitations include:

- It expects a specific VEP TSV column structure.
- It writes `ranked.tsv` to the current working directory.
- It does not currently accept a custom output path.
- It does not sort the output rows by rank.
- It does not yet combine phenotype fit, inheritance model, case-level metadata, or expert review feedback.
- It should not be used as a clinical decision system without validation.

## Suggested Next Improvements

- Add command-line options for input and output paths.
- Sort output by `Rank`.
- Preserve skipped rows in a separate file with skip reasons.
- Add unit tests with a small synthetic VEP TSV fixture.
- Add phenotype-aware ranking features.
- Map top-ranked variants into the expert board review room.
- Add provenance fields explaining which rule assigned each rank.

