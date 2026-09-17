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
def score_clinvar(info):
    '''score will be 0-5, with 5 being the highest priority'''
    try:
        clnsig=info.split("CLNSIG=")[1].split(";")[0]
        review_star=int(info.split("REVIEW_STAR=")[1].split(";")[0])
    
        if clnsig == "Pathogenic" or clnsig == "Likely_pathogenic":
            if review_star >= 3: ## expert panel (3) or practice guidelines (4)
                score=5
            elif review_star >= 1: ## single (1) or multiple (2) submitters
                score=4
            else: ## review_star==0, no evidence / conflicting
                score=3
        elif clnsig == "Uncertain_significance":
            score=2
        else: ## Benign or Likely_benign
            if review_star < 3: # with conflicting eveidence
                score=1
            else: # high confidence benign or likely benign
                score=0

    except IndexError:
        clnsig="."
        score=-1

    return score, clnsig

def score_gnomad(info):
    '''score will 0-3, with 3 being the highest priority'''
    try:
        gnomad_af=float(info.split("GNOMAD_AF=")[1].split(";")[0])
        gnomad_af_grpmax=float(info.split("GNOMAD_AF_GRPMAX=")[1].split(";")[0])
        gnomad_af_eas=float(info.split("GNOMAD_AF_EAS=")[1].split(";")[0])
        gnomad_af_sas=float(info.split("GNOMAD_AF_SAS=")[1].split(";")[0])

        if gnomad_af_grpmax <= AF_THRESHOLD: ## low AF in all populations, prioritize 
            score=3
        elif gnomad_af_eas <= AF_THRESHOLD and gnomad_af_sas <= AF_THRESHOLD: ## grpmax is > 0.05, but low AF in EAS and SAS
            score=2
        elif gnomad_af_eas <= AF_THRESHOLD or gnomad_af_sas <= AF_THRESHOLD: ## grpmax is > 0.05, but low AF in either EAS or SAS
            score=1
        else:
            score=0

    except IndexError:
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
        if clinvar[0]==5:
            rank=1
        elif clinvar[0]>1: ## not benign or likely benign
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
            if clinvar[0]==1: ## with conflicting evidence
                rank=7
            else: ## clinvar[0]==0
                rank=8

        parsed_info.append([chrom, pos, rsid, ref, alt, gene, hgvsc, hgvsp, clinvar[1], gnomad[1], gnomad[2], gnomad[3], gnomad[4], impact, alphamissense, cadd, revel, spliceai, rank])

    return(parsed_info)

if __name__=='__main__':
    # parse vcf
    vcf_entries=vcf_parser(vcf)

    ## Print Headers
    print("chrom, pos, rsid, ref, alt, gene, hgvsc, hgvsp, clnsig, gnomad_af, gnomad_af_grpmax, gnomad_af_eas, gnomad_af_sas, impact, alphamissense, cadd, revel, spliceai, rank")
    for entry in vcf_entries:
        print(",".join([str(x) for x in entry]))
