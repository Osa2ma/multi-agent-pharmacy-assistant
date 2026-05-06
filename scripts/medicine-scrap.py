"""
Pharmacy Assistant - Drug Label Downloader
Fetches structured drug labels from OpenFDA for the RAG knowledge base.

Usage:
    pip install requests
    python download_labels.py

Output:
    drug_labels_json/
        metformin.json
        metformin.meta.json
        ...
"""

import requests
import json
import os
import time
from datetime import datetime



DRUGS = [
    # --- Diabetes ---
    "metformin",
    "glibenclamide",       
    "gliclazide",          
    "sitagliptin",
    "empagliflozin",
    "insulin glargine",
    "insulin aspart",

    # --- Cardiovascular: Antihypertensives ---
    "lisinopril",
    "ramipril",
    "captopril",         
    "enalapril",
    "losartan",
    "valsartan",
    "amlodipine",
    "nifedipine",
    "metoprolol",
    "bisoprolol",
    "atenolol",
    "carvedilol",
    "hydrochlorothiazide",
    "furosemide",
    "spironolactone",
    "indapamide",       

    # --- Cardiovascular: Lipids & Antiplatelets ---
    "atorvastatin",
    "rosuvastatin",
    "simvastatin",
    "clopidogrel",
    "aspirin",
    "warfarin",
    "rivaroxaban",
    "apixaban",

    # --- Pain / Inflammation (NSAIDs heavily used in Egypt) ---
    "ibuprofen",
    "paracetamol",
    "acetaminophen",
    "diclofenac",          
    "naproxen",
    "meloxicam",
    "ketorolac",
    "celecoxib",
    "tramadol",            
    "codeine",

    # --- Antibiotics (high use in Egypt) ---
    "amoxicillin",
    "amoxicillin and clavulanate",   
    "azithromycin",
    "clarithromycin",
    "erythromycin",
    "ciprofloxacin",
    "levofloxacin",
    "doxycycline",
    "cephalexin",
    "cefuroxime",
    "ceftriaxone",
    "metronidazole",       
    "trimethoprim and sulfamethoxazole",  
    "nitrofurantoin",

    # --- GI ---
    "omeprazole",
    "pantoprazole",
    "esomeprazole",
    "ranitidine",
    "famotidine",
    "domperidone",        
    "metoclopramide",
    "loperamide",
    "ondansetron",
    "hyoscine butylbromide",  

    # --- Respiratory ---
    "albuterol",           
    "salbutamol",
    "salmeterol",
    "fluticasone",
    "budesonide",
    "montelukast",
    "ipratropium",

    # --- Antihistamines (heavy use in Egypt) ---
    "loratadine",
    "cetirizine",
    "fexofenadine",
    "chlorpheniramine",  
    "diphenhydramine",

    # --- Mental health ---
    "sertraline",
    "escitalopram",
    "citalopram",
    "fluoxetine",
    "paroxetine",
    "venlafaxine",
    "duloxetine",
    "bupropion",
    "trazodone",
    "amitriptyline",
    "diazepam",
    "alprazolam",
    "clonazepam",
    "risperidone",
    "olanzapine",
    "quetiapine",

    # --- Neurology ---
    "gabapentin",
    "pregabalin",
    "carbamazepine",
    "valproic acid",
    "levetiracetam",
    "phenytoin",

    # --- Endocrine / Bone ---
    "levothyroxine",
    "prednisone",
    "prednisolone",
    "dexamethasone",
    "hydrocortisone",
    "alendronate",

    # --- Urology ---
    "tamsulosin",
    "finasteride",
    "sildenafil",

    # --- Other commonly dispensed ---
    "vitamin d",
    "folic acid",
    "iron",
    "calcium carbonate",
    "potassium chloride",
]


DRUGS = list(dict.fromkeys(DRUGS))



OUTPUT_DIR = r"C:\Users\pc\Desktop\pharmacy-assisstant\docker\medical-docs"
BASE_URL = "https://api.fda.gov/drug/label.json"
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 0.3   
RETRY_DELAY = 2                
MAX_RETRIES = 2


RELEVANT_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "dosage_forms_and_strengths",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "boxed_warning",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "pregnancy",
    "nursing_mothers",
    "pediatric_use",
    "geriatric_use",
    "overdosage",
    "mechanism_of_action",
    "clinical_pharmacology",
    "how_supplied",
    "storage_and_handling",
    "patient_information",
    "information_for_patients",
]




def safe_filename(name: str) -> str:
    """Convert a drug name into a safe filename."""
    return name.replace(" ", "_").replace("/", "_").replace("\\", "_").lower()


def fetch_drug_label(drug_name: str) -> dict | None:
    """
    Query OpenFDA for a drug label. Tries generic_name first,
    then brand_name as a fallback.
    """
    queries = [
        f'openfda.generic_name:"{drug_name}"',
        f'openfda.substance_name:"{drug_name}"',
        f'openfda.brand_name:"{drug_name}"',
    ]

    for query in queries:
        params = {"search": query, "limit": 1}
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = requests.get(
                    BASE_URL, params=params, timeout=REQUEST_TIMEOUT
                )
                if response.status_code == 404:
                    break  # try next query strategy
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                if results:
                    return results[0]
                break
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES:
                    print(f"    Retry {attempt + 1}/{MAX_RETRIES} after error: {e}")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"    Failed after {MAX_RETRIES} retries: {e}")
    return None


def trim_label(label: dict) -> dict:
    """
    Keep only the clinically relevant sections plus the openfda metadata.
    Reduces file size and noise for RAG.
    """
    trimmed = {"openfda": label.get("openfda", {})}
    for section in RELEVANT_SECTIONS:
        if section in label:
            trimmed[section] = label[section]
    return trimmed


def build_metadata(drug_name: str, label: dict) -> dict:
    """Build a metadata sidecar file - useful for RAG source attribution."""
    openfda = label.get("openfda", {})
    return {
        "drug_query": drug_name,
        "generic_names": openfda.get("generic_name", []),
        "brand_names": openfda.get("brand_name", []),
        "manufacturer_names": openfda.get("manufacturer_name", []),
        "product_type": openfda.get("product_type", []),
        "route": openfda.get("route", []),
        "rxcui": openfda.get("rxcui", []),
        "spl_id": label.get("id"),
        "spl_set_id": label.get("set_id"),
        "effective_time": label.get("effective_time"),
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "source": "OpenFDA - api.fda.gov/drug/label.json",
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {os.path.abspath(OUTPUT_DIR)}")
    print(f"Drugs to fetch: {len(DRUGS)}")
    print("=" * 60)

    success = []
    failed = []

    for i, drug in enumerate(DRUGS, start=1):
        print(f"[{i:3}/{len(DRUGS)}] {drug}")
        label = fetch_drug_label(drug)

        if not label:
            print(f"    No results found")
            failed.append(drug)
            time.sleep(DELAY_BETWEEN_REQUESTS)
            continue

        fname = safe_filename(drug)

        trimmed = trim_label(label)
        with open(f"{OUTPUT_DIR}/{fname}.json", "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2, ensure_ascii=False)

        # Save metadata sidecar
        meta = build_metadata(drug, label)
        with open(f"{OUTPUT_DIR}/{fname}.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        brand_display = (
            ", ".join(meta["brand_names"][:2]) if meta["brand_names"] else "—"
        )
        print(f"    Saved (brands: {brand_display})")
        success.append(drug)
        time.sleep(DELAY_BETWEEN_REQUESTS)


    print("=" * 60)
    print(f"SUCCESS: {len(success)}")
    print(f"FAILED:  {len(failed)}")
    if failed:
        print("\nDrugs not found on OpenFDA:")
        for d in failed:
            print(f"  - {d}")
        print(
            "\nNote: failed drugs may be available in Egypt but not registered "
            "with the FDA. You can supplement these from the Egyptian Drug "
            "Authority (EDA) or DailyMed manually."
        )

    # Save a run log
    log_path = f"{OUTPUT_DIR}/_run_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_at": datetime.utcnow().isoformat() + "Z",
                "total_requested": len(DRUGS),
                "successful": success,
                "failed": failed,
            },
            f,
            indent=2,
        )
    print(f"\nRun log saved to: {log_path}")


if __name__ == "__main__":
    main()