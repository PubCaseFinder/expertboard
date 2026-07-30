#!/usr/bin/env python
'''
This script will take a VEP output (TSV) and prioritize variants
based on the following:
    1. Clinvar Annotation
        - CLNREVSTAT: reviewed_by_expert_panel, no_conflicts
        - CLNSIG: Pathogenic, Likely_Pathogenic, VUS
    2. Population Allele Frequencies
        - local AF
        - gnomad AF
    3. In Silico Tools
        - REVEL, SpliceAI, Alphamissense, CADD
    4. Impact: High, Moderate > Low
'''

## Import Libraries
from sys import argv
import csv

## Thresholds
AF=0.05 ## <0.05 in SG10K, gnomADg, gnomADg_eas, gonmADg_sas
CONF=4 ## >=4 patho or likely_patho reports
REVEL=0.5 ## >=0.5 revel score
#CADD=10 ## >=10 cadd score
SPLICEAI=0.20 ## >=0.20 spliceAI score
#ALPHAMISSENSE=0.34 ## > 0.34 alphamissense score

## Functions
def readtsv(tsv):
    with open(tsv, mode="r", encoding="utf-8") as f, open("ranked.tsv","w") as outfile:
        ## read TSV
        reader=csv.DictReader(f, delimiter="\t")

        ## Get headers and add "Rank" column
        fieldnames=reader.fieldnames + ["Rank"]

        ## Initialize writer and write headers to outfile
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()

        ## Add variant ranking
        for row in reader:
            row["Rank"]=100 ## Initialize Rank
            
            ## Filter based on MANE, HGCN, HGVSc
            if (
                    "MANE" not in row["Transcript_Type"] 
                    or row["SYMBOL_SOURCE"]!="HGNC"
                    or (row["HGVSc"]=="" or row["HGVSc"]==".")
                ):
                continue
            
            ## Check ClinVar annotations
            if "Pathogenic" in row["ClinVar_CLNSIG"] or "Likely_pathogenic" in row["ClinVar_CLNSIG"]:
                if "reviewed_by_expert_panel" in row["ClinVar_CLNREVSTAT"]: ## RANK 1: Pathogenic or Likely_pathogenic, reviewed by expert panel
                    row["Rank"]=1
                elif "no_conflicts" in row["ClinVar_CLNREVSTAT"]: ## RANK 2: Pathogenic or Likely_pathogenic, no conflicts
                    row["Rank"]=2

                elif "conflicting_classifications" in row["ClinVar_CLNREVSTAT"]: ## RANK 2,3: Pathogenic or Likely_pathogenic, conflicting_classifications
                    try:
                        num_patho=int(row["ClinVar_CLNSIGCONF"].split("Pathogenic(")[1].split(")")[0])
                    except:
                        num_patho=0
                    try:
                        num_likely_patho=int(row["ClinVar_CLNSIGCONF"].split("Likely_pathogenic(")[1].split(")")[0])
                    except:
                        num_likely_patho=0

                    reports=num_patho+num_likely_patho
                    if reports>=CONF: ## RANK 3: Pathogenic or Likely_pathogenic, conflicting_classifications, >=4 reports
                        row["Rank"]=3
                    elif reports<CONF: ## RANK 4: Pathogenic or Likely_pathogenic, conflicting_classifications, <4 reports
                        row["Rank"]=4
                    
            elif row["ClinVar_CLNSIG"]=="Uncertain_significance":
                if  "reviewed_by_expert_panel" in row["ClinVar_CLNREVSTAT"]: ## RANK 150: Uncertain Significance, reviewed by expert panel
                    row["Rank"]=150
                else: ## RANK 5: Uncertain Significance
                    row["Rank"]=5

            elif "Benign" in row["ClinVar_CLNSIG"] or "Likely_benign" in row["ClinVar_CLNSIG"]:
                if "no_conflicts" in row["ClinVar_CLNREVSTAT"]: ## RANK 200: Benign or Likely_benign, no_conflicts
                    row["Rank"]=200
                elif "reviewed_by_expert_panel" in row["ClinVar_CLNREVSTAT"]: ## RANK 300: Benign or Likely_benign, reviewed by expert panel
                    row["Rank"]=300

            ## Check in silico scores
            ## RANK 6: In silico score >= threshold
            elif (
                    (row["REVEL_score"]!="" and float(row["REVEL_score"])>=REVEL)
                    or (row["SpliceAI_max"]!="" and float(row["SpliceAI_max"])>=SPLICEAI)
                ):
                row["Rank"]=6

            ## Check allele frequencies (SG10K, gnomad, gnomad_eas, gnomad_sas)
            ## RANK 7: Low population allele frequencies
            elif (
                    (row["SG10K_AF"]!="" and not float(row["SG10K_AF"])>AF) 
                    and (row["gnomADg_4_AF"]!="" and not float(row["gnomADg_4_AF"])>AF)
                    and (row["gnomADg_4_AF_eas"]!="" and not float(row["gnomADg_4_AF_eas"])>AF)
                    and (row["gnomADg_4_AF_sas"]!="" and not float(row["gnomADg_4_AF_sas"])>AF)
                ):
                row["Rank"]=7

            ## Check IMPACT
            elif row["IMPACT"].upper()=="HIGH": ## RANK 8: High Impact Variant
                row["Rank"]=8
            elif row["IMPACT"].upper()=="MODERATE": ## RANK 9: Moderate Impact Variant
                row["Rank"]=9
            elif row["IMPACT"].upper()=="LOW": ## RANK 10: Low Impact Variants
                row["Rank"]=10

            ## write output
            writer.writerow(row)

## Main
if __name__=="__main__":
    tsv=readtsv(argv[1])
    print("Done.")
