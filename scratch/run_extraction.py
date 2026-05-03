import sys
import json
from pathlib import Path

# Add project root to sys.path to allow imports
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from extraction.esg_pipeline import ESGExtractor

def main():
    doc_id = "2025-boeing-sustainability-report"
    print(f"=== Testing ESG Extraction on {doc_id} ===")
    
    # Initialize extractor (this will load models via load_models())
    print("[*] Loading ESGExtractor (this will load the models...)")
    extractor = ESGExtractor(doc_id)
    
    # Query something related to emissions
    query = "Scope 1 and 2 emissions"
    print(f"[*] Querying text for: '{query}'")
    text_facts = extractor.extract_from_text(query)
    
    print("\n[Text Facts Found]")
    print(json.dumps(text_facts, indent=2))
    
    # Also test table extraction if tables exist
    json_path = Path("data/outputs") / f"{doc_id}_tables.json"
    print(f"[*] Querying tables from: {json_path}")
    table_facts = extractor.extract_from_tables(str(json_path))
    
    print("\n[Table Facts Found]")
    # Print first 5 table facts to avoid overwhelming output
    print(json.dumps(table_facts[:5], indent=2))
    
    # Test merge
    print("\n[*] Merging facts...")
    merged = extractor.merge_and_normalize(text_facts, table_facts)
    print(f"Total merged facts: {len(merged)}")
    
if __name__ == "__main__":
    main()
