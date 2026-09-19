#!/usr/bin/env python
'''
This script will take a ClinVar, Gnomad, and VEP annotated VCF 
and prioritize variants based on the following:
    1. Clinvar Annotation
        - CLNREVSTAT: reviewed_by_expert_panel, no_conflicts
        - CLNSIG: Pathogenic, Likely_Pathogenic, VUS, Conflicting
    2. Population Allele Frequencies
        - local AF (if present)
        - gnomad AF (including EAS and SAS)
    3. In Silico Tools (!!! SKIP FOR NOW !!!)
        - REVEL, SpliceAI, Alphamissense, CADD
    4. Impact: High, Moderate > Low

Highest Priority will be Rank 1

note: This script is written by Francis T.
'''

## Import Libraries
from sys import argv

vcf=argv[1]

## Thresholds
AF_THRESHOLD=0.05 ## gnomAD allele frequencies

#REVEL=0.5 ## >=0.5 revel score
#CADD=10 ## >=10 cadd score
#SPLICEAI=0.20 ## >=0.20 spliceAI score
#ALPHAMISSENSE=0.34 ## > 0.34 alphamissense score

## Functions
def _field(info, key):
    '''Return the raw INFO value for key, or None if the field is absent.'''
    marker = key + "="
    if marker not in info:
        return None
    return info.split(marker)[1].split(";")[0]

_MISSING_TOKENS = {"", "-", "na", "n/a", ".", "null", "none"}

def _as_float(value):
    '''Treat missing/placeholder values (absent, 0, -, NA, .) as 0.0'''
    value = (value or "").strip()
    if value.lower() in _MISSING_TOKENS:
        return 0.0
    return float(value)

def _as_int(value):
    '''Treat missing/placeholder values (absent, 0, -, NA, .) as 0'''
    value = (value or "").strip()
    if value.lower() in _MISSING_TOKENS:
        return 0
    return int(value)

def score_clinvar(info):
    '''score will be 0-4, with 4 being the highest priority'''
    try:
        clnsig=info.split("CLNSIG=")[1].split(";")[0]
        review_star=_as_int(_field(info, "REVIEW_STAR"))
    
        if clnsig == "Pathogenic" or clnsig == "Likely_pathogenic":
            if review_star >= 3: ## expert panel (3) or practice guidelines (4)
                score=4
            elif review_star >= 1: ## single (1) or multiple (2) submitters
                score=3
            else: ## review_star==0, no evidence / conflicting
                score=2
        elif clnsig == "Uncertain_significance":
            score=1
        else: ## Benign or Likely_benign
            score=0
    except IndexError:
        clnsig="."
        score=-1

    return score, clnsig

def score_gnomad(info):
    '''score will 0-3, with 3 being the highest priority'''
    try:
        # A field missing entirely (not annotated / not found in gnomAD) is
        # treated the same as an explicit 0/-/NA: not observed = rare.
        gnomad_af=_as_float(_field(info, "GNOMAD_AF"))
        gnomad_af_grpmax=_as_float(_field(info, "GNOMAD_AF_GRPMAX"))
        gnomad_af_eas=_as_float(_field(info, "GNOMAD_AF_EAS"))
        gnomad_af_sas=_as_float(_field(info, "GNOMAD_AF_SAS"))

        if gnomad_af_grpmax <= AF_THRESHOLD: ## low AF in all populations, prioritize 
            score=3
        elif gnomad_af_eas <= AF_THRESHOLD and gnomad_af_sas <= AF_THRESHOLD: ## grpmax is > 0.05, but low AF in EAS and SAS
            score=2
        elif gnomad_af_eas <= AF_THRESHOLD or gnomad_af_sas <= AF_THRESHOLD: ## grpmax is > 0.05, but low AF in either EAS or SAS
            score=1
        else:
            score=0

    except (TypeError, ValueError):
        gnomad_af='.'
        gnomad_af_grpmax='.'
        gnomad_af_eas='.'
        gnomad_af_sas='.'
        score=-1
    return score, gnomad_af, gnomad_af_grpmax, gnomad_af_eas, gnomad_af_sas

def score_alphamissense(info):
    return 0

def score_cadd(info):
    return 0

def score_revel(info):
    return 0

def score_spliceai(info):
    return 0


def score_priority(info):
    """Return the Francis priority rank for one VCF INFO string."""
    clinvar_score = score_clinvar(info)[0]
    gnomad_score = score_gnomad(info)[0]
    impact = info.split("VEP_IMPACT=")[1].split(";")[0]

    if clinvar_score == 4:
        return 1
    if clinvar_score > 0:
        return {3: 2, 2: 3, 1: 4}.get(gnomad_score, 5)
    if clinvar_score == -1:
        return 5 if impact in ("HIGH", "MODERATE") else 6
    return 7

def vcf_parser(vcf):
    ## iterate over vcf entries
    entries=[x for x in open(vcf).readlines() if not x.startswith("#") and x != ""]
    parsed_info=[]
    for entry in entries:
        entry=entry.split("\t")
        chrom=entry[0].strip()
        pos=entry[1].strip()
        rsid=entry[2].strip()
        ref=entry[3].strip()
        alt=entry[4].strip()
        info=entry[7]
         
        # Check if MANE_HIT=Yes, if not continue (skip non-MANE); minimize duplicated entries 
        mane=info.split("MANE_HIT=")[1].split(";")[0]
        if mane=="No":
            continue

        # For MANE hits, parse info field
        # VEP Annotations
        clinvar=score_clinvar(info) ## -1 score means no information
        gnomad=score_gnomad(info) ## -1 score means no information
        impact=info.split('VEP_IMPACT=')[1].split(';')[0]
        try:
            hgvsc=info.split('VEP_HGVSC=')[1].split(';')[0]
        except IndexError:
            hgvsc='.'
        try:
            hgvsp=info.split('VEP_HGVSP=')[1].split(';')[0]
        except IndexError:
            hgvsp='.'
        gene=info.split('GENE=')[1].split(';')[0]

        # VEP in silico scores
        alphamissense=score_alphamissense(info)
        cadd=score_cadd(info)
        revel=score_revel(info)
        spliceai=score_spliceai(info)

        # resolve ranking
        if clinvar[0]==4:
            rank=1
        elif clinvar[0]>0: ## not benign or likely benign
            if gnomad[0]==3:
                rank=2
            elif gnomad[0]==2:
                rank=3
            elif gnomad[0]==1:
                rank=4
        elif clinvar[0]==-1:
            if impact=='HIGH' or impact=='MODERATE':
                rank=5
            elif impact=='LOW' or impact=='MODIFIER':
                rank=6
        else: ## benign or likely benign
            rank=7

        parsed_info.append([chrom, pos, rsid, ref, alt, gene, hgvsc, hgvsp, clinvar[1], gnomad[1], gnomad[2], gnomad[3], gnomad[4], impact, alphamissense, cadd, revel, spliceai, rank])

    return(parsed_info)

if __name__=='__main__':
    # parse vcf
    vcf_entries=vcf_parser(vcf)

    ## Print Headers
    print("chrom, pos, rsid, ref, alt, gene, hgvsc, hgvsp, clnsig, gnomad_af, gnomad_af_grpmax, gnomad_af_eas, gnomad_af_sas, impact, alphamissense, cadd, revel, spliceai, rank")
    for entry in vcf_entries:
        print(",".join([str(x) for x in entry]))
