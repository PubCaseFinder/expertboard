# Variant Review

## Purpose

Variant Review in ExpertBoard is an ACMG-style evidence workbench for a pre-filtered candidate variant list.

ExpertBoard is not intended to perform primary variant calling, genome-wide filtering, or full variant discovery. The expected input is a short VCF containing approximately 10-20 candidate variants that have already passed an upstream filtering step.

The goal is to help reviewers prioritize, annotate, discuss, and decide which evidence items should be accepted, rejected, or kept pending in the clinical context of the case.

## Input assumption

| Item | Assumption |
|---|---|
| Input file | Pre-filtered candidate VCF |
| Variant count | Approximately 10-20 variants |
| Scope | One patient or a small cohort |
| Context | Known phenotype, unknown phenotype, one gene, multi-gene, or same-condition cohort |
| Not in scope | Variant calling, genome-wide filtering, raw WGS/WES prioritization, coverage/QC workflows |

Example sample file:

```text
sample-data/synthetic_patient_HCM_variants.vcf
```

## What Variant Review should do

| Step | Description | Output |
|---|---|---|
| Read candidate VCF | Import variants from a pre-filtered shortlist VCF | Variant table |
| Normalize variant context | Extract gene, HGVS, variant type, genotype, and submitted notes | Structured variant rows |
| Prioritize variants | Rank candidates by gene, condition relevance, phenotype match, existing annotations, and ACMG-style evidence candidates | Review priority |
| Create evidence boxes | Group evidence by source, such as population database, in silico prediction, literature, segregation, and functional data | Evidence workbench |
| Propose ACMG-style candidates | Suggest possible criteria candidates without automatically accepting them | Candidate criteria |
| Support reviewer decision | Let experts accept, reject, or keep criteria pending | Board-reviewed evidence state |

## What Variant Review should not do

| Not in scope | Reason |
|---|---|
| Primary variant discovery | The VCF is already pre-filtered |
| Raw VCF filtering from thousands of variants | Too broad for the hackathon MVP |
| Fully automated ACMG classification | Many criteria require clinical judgment |
| Replacing expert review | ExpertBoard is designed for human-governed decisions |
| Replacing tools such as Franklin | ExpertBoard can use variant interpretation outputs as evidence inputs |

## Evidence sources and proposed criteria

| Evidence source | Data to collect | Proposed criteria | Automation level | Reviewer role |
|---|---|---|---|---|
| Population databases | gnomAD, All of Us, local databases such as SG/JPN | `BA1`, `BS1`, `PM2_P` | Semi-automated | Confirm based on disease incidence, inheritance, gene, and population |
| In silico predictors | AlphaMissense, REVEL, CADD, PolyPhen, SIFT, splice predictors | `PP3`, `BP4`, `BP7` | Automated to semi-automated | Review variant type and tool suitability |
| Phenotype match | Patient or cohort phenotype, HPO terms, disease specificity | `PP4`, `BP5` | Manual | Clinical reviewer confirms phenotype fit |
| Literature and case reports | Published cases, ClinVar notes, submitter evidence, local knowledge base | `PS4`, `PS3`, `BS3` | Semi-automated | Review paper quality and evidence strength |
| Family segregation | Parental testing, phase, affected relatives, unaffected relatives | `PS2`, `PM3`, `PM6`, `PP1`, `BS4`, `BP2` | Manual | Requires family and clinical data |
| Functional assay | In vitro, in vivo, RNA, protein, or validated assay evidence | `PS3`, `BS3` | Semi-automated | Confirm assay validity and disease relevance |
| Variant type and gene mechanism | LoF, missense, indel, splice, synonymous; known disease mechanism | `PVS1`, `PM4`, `BP3`, `PP2`, `BP1` | Automated to semi-automated | Confirm gene-disease mechanism |
| Amino acid or residue evidence | Same amino acid change or same residue with known pathogenic variant | `PS1`, `PM5` | Automated to semi-automated | Confirm equivalence and avoid splice confounding |

## Automation categories

The key design principle is to separate evidence preparation from expert acceptance.

| Category | Meaning | Examples |
|---|---|---|
| Automated | The system can propose the criterion from structured data with minimal manual input | `PP3/BP4` from in silico tools, `PS1/PM5` from known amino acid changes |
| Semi-automated | The system can gather evidence, but the reviewer must confirm interpretation | `PM2_P`, `BA1`, `BS1`, `PS3/BS3`, `PS4`, `PVS1` |
| Manual | The system can display missing data or capture reviewer input, but cannot decide | `PS2`, `PM6`, `PP1`, `BS4`, `PM3`, `BP2`, `PP4` |

## Criteria-level interpretation

| Criteria group | Practical ExpertBoard interpretation |
|---|---|
| `PVS1` | Can be semi-automated using variant type and gene LoF mechanism, potentially supported by AutoPVS1-style logic. Reviewer confirms gene-disease mechanism and caveats. |
| `PS1`, `PM5` | Can be automated or semi-automated by comparing amino acid changes and known pathogenic variants. Reviewer confirms equivalence and splice caveats. |
| `PS2`, `PM6` | Cannot be automated reliably because they require de novo and parental confirmation data. |
| `PS3`, `BS3` | Literature and functional data can be gathered automatically, but assay quality and disease relevance require expert confirmation. |
| `PS4` | Literature search can help, but prevalence enrichment and case-control strength require reviewer judgment. |
| `PM1` | Can be semi-automated using known domains and hotspots, but needs gene-specific context. |
| `BA1`, `BS1`, `BS2`, `PM2_P` | Population frequency can be retrieved, but interpretation depends on disease incidence, inheritance, penetrance, and population. |
| `PM3`, `BP2` | Require phase, inheritance, and segregation data, so they are mostly manual. |
| `PM4`, `BP3` | Can use variant type and sequence context, but repeat regions and functional domains may need review. |
| `PP1`, `BS4` | Require segregation data and disease association; system can track evidence but not decide automatically. |
| `PP2`, `BP1` | Can be semi-automated using gene mechanism, variant type, and disease correlation. |
| `PP3`, `BP4`, `BP7` | Can be automated from prediction tools, but should be counted only once per variant evaluation and interpreted by variant type. |
| `PP4`, `BP5` | Require clinical context and phenotype review; they should connect directly to the Phenotype Review workspace. |

## Suggested UI model

Variant Review should show candidate variants first, then evidence boxes for the selected variant.

### Candidate variant table

| Column | Example |
|---|---|
| Priority | 1 |
| Gene | `MYH7` |
| Variant | `c.1988G>A p.Arg663His` |
| Variant type | Missense |
| Current annotation | Pathogenic / VUS / Likely benign |
| Condition relevance | HCM-related gene |
| Evidence status | 3 candidate criteria, 2 pending |
| Reviewer state | Needs review |

### Evidence box

| Field | Example |
|---|---|
| Criterion | `PM2_P candidate` |
| Evidence source | Population databases |
| System suggestion | Variant appears rare or absent |
| Automation level | Semi-automated |
| Reviewer decision | Accept / Reject / Pending |
| Reviewer note | Confirm against disease incidence and ancestry |

## Recommended MVP scope

For the hackathon MVP, the most useful implementation is:

| MVP item | Notes |
|---|---|
| Import the synthetic shortlist VCF | Use `sample-data/synthetic_patient_HCM_variants.vcf` |
| Display candidate variant table | 10-20 rows is enough |
| Show evidence boxes for one selected variant | Start with population, in silico, phenotype, literature, segregation, functional |
| Label each criterion by automation level | Automated / semi-automated / manual |
| Allow reviewer state | Accept / Reject / Pending can be mocked first |
| Connect phenotype-dependent evidence to Phenotype Review | Especially `PP4` |

## Core message

ExpertBoard should not be framed as a fully automated ACMG classifier.

It should be framed as a human-governed evidence workbench:

```text
The system prepares candidate evidence.
The expert board decides what counts.
```
