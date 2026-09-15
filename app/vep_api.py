#!/usr/bin/env python
'''
API Script to batch annotate with VEP
created by Francis Tablizo 
'''

import json
import time
import requests
from sys import argv

vcf=argv[1] ## input VCF 

## ==============
## FUNCTIONS
## ==============

def get_variant_list(vcf):
    """Parses a vcf file to return a list of variants
    my_variants=["chrom start end ref/alt strand"]
    """
    my_variants=[]
    with open(vcf,'r') as f:
        for line in f:
            if not line.startswith("#"):
                line=line.split("\t")
                chrom=line[0].strip()
                start=line[1].strip()
                alt=line[4].strip()
                end=int(start)+(len(alt)-1)
                my_variants.append("{0}:{1}-{2}/{3}".format(chrom,start,end,alt))
    return my_variants

def get_vep_annotations(variants, genome_build="GRCh38"):
    """Fetches VEP annotations via the Ensembl REST API using a POST batch request.

    Parameters:
        variants (list): List of variant strings, e.g., ["21:26960011-26960011/A", "9:22125503-22125503/C"]
        genome_build (str): "GRCh38" (default) or "GRCh37"
    """

    # Handle retries
    max_retries = 10
    attempts = 0

    # Choose server depending on the target assembly
    if genome_build.upper() == "GRCh38":
        server = "https://grch38.rest.ensembl.org"
    else:
        server = "https://rest.ensembl.org"

    endpoint = "/vep/human/region"
    url = f"{server}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Formulate the payload object
    payload = {
            "variants": variants,
            "refseq": 1,
            "hgvs": 1,
            "CADD": 1,
            "AlphaMissense": 1,
            "dbNSFP": "REVEL_score",
            "SpliceAI": 1
            }

    max_retries = 10
    attempts = 0
    status_codes = [429, 500, 503]

    while attempts < max_retries:
        response = requests.post(
            url, headers=headers, data=json.dumps(payload)
        )

        # 1. Handle Rate Limiting and Server Errors gracefully
        if response.status_code in status_codes:
            attempts += 1

            if attempts >= max_retries:
                print(
                    f"Failed after {max_retries} attempts. Final status: {response.status_code}", file=sys.stderr
                )
                break  # Break out of loop so raise_for_status() can catch it at the end

            # Ensembl VEP API explicitly sends a "Retry-After" header when rate-limited (429)
            retry_after = int(response.headers.get("Retry-After", 5))
            print(
                f"Status {response.status_code}. Retrying after {retry_after} seconds... (Attempt {attempts}/{max_retries})", file=sys.stderr
            )
            time.sleep(retry_after)
            continue  # Re-run the loop for a fresh attempt

        # 2. If it's NOT a 429/500/503, it's either a success (200) or a fatal error (404, 400).
        else:
            break

    # 3. Triggers an exception if the final loop outcome was an error (e.g., 400, 404, or unrecovered 429/500)
    response.raise_for_status()

    # 4. Return successful JSON data
    return response.json()

## =========
## MAIN
## =========
if __name__ == "__main__":
    # Format requirements: chromosome:start-end:strand/allele 
    my_variants = get_variant_list(vcf)
    annotations = get_vep_annotations(my_variants, genome_build="GRCh38")
    
    if annotations:
        for entry in annotations:       
            variant_id = entry.get("input")
            consequence = entry.get("most_severe_consequence",".") 

            ## Extract transcript annotation information
            transcripts = entry.get("transcript_consequences", [])
            for tx in transcripts:
                gene = tx.get("gene_symbol",".")
                tx_id = tx.get("transcript_id", ".")
                biotype = tx.get("biotype", ".")
                
                hgvsc = tx.get("hgvsc",".")
                hgvsp = tx.get("hgvsp",".")

                ## Resolve in silico predictions

                # alphamissense
                alpham = tx.get("alphamissense",{}).get("am_pathogenicity",".")

                # cadd
                cadd = tx.get("cadd_phred",".")

                # spliceai
                spliceai = tx.get("spliceai",{})
                if spliceai != {}:
                    numeric_spliceai = [x for x in spliceai.values() if isinstance(x, (int,float))]
                    spliceai_max = max(numeric_spliceai) 
                else:
                    spliceai = "."

                # revel
                revel = tx.get("revel_score")
                if revel != None:
                    revel = max([float(x) for x in revel.split(",") if x!="."], default=0)
                else:
                    revel = 0
                
                ## print output
                print(f"{gene},{tx_id},{biotype},{hgvsc},{hgvsp},{alpham},{cadd},{revel},{spliceai_max}")
