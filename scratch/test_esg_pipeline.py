import os
import sys
import json
import tempfile
from pathlib import Path

# Add project root to sys.path to allow imports
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Mock LangSmith to prevent errors if not configured
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from extraction.esg_pipeline import DocumentIngestor, ESGExtractor, evaluate_run
from config import INDEX_STORAGE_PATH

def main():
    print("=== Testing ESG Data Extraction Pipeline ===")
    
    # 1. Setup mock data
    doc_id = "test_doc_001"
    
    # Create temp markdown
    md_content = """# Sustainability Report 2023
    Our company is committed to reducing emissions. 
    In 2023, our Scope 1 Emissions reached 1000 tonnes.
    We are actively tracking water usage and social metrics.
    """
    
    # Create temp JSON table
    tables_data = [
        {
            "table_index": 0,
            "data": {
                "data": {
                    "grid": [
                        [{"text": "Metric", "column_header": True}, {"text": "2023", "column_header": True}],
                        [{"text": "Scope 1 Emissions", "row_header": True}, {"text": "950"}],
                        [{"text": "Water Usage", "row_header": True}, {"text": "50000"}]
                    ]
                }
            }
        }
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / f"{doc_id}.md"
        json_path = Path(tmpdir) / f"{doc_id}_tables.json"
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(tables_data, f)
            
        # 2. Test Ingestion
        print("\n--- Phase 1: Ingestion ---")
        ingestor = DocumentIngestor()
        index = ingestor.ingest(str(md_path), doc_id)
        print(f"Index created and persisted to {INDEX_STORAGE_PATH / doc_id}")
        
        # 3. Test Extraction
        print("\n--- Phase 2: Extraction ---")
        extractor = ESGExtractor(doc_id)
        
        text_facts = extractor.extract_from_text("Scope 1 Emissions")
        print(f"Text Facts: {json.dumps(text_facts, indent=2)}")
        
        table_facts = extractor.extract_from_tables(str(json_path))
        print(f"Table Facts: {json.dumps(table_facts, indent=2)}")
        
        # 4. Test Merging & Normalization
        print("\n--- Phase 3: Merging ---")
        # Ensure we add some mock units since the table mock doesn't have them
        for fact in table_facts:
            if "Scope 1" in fact.get("metric", ""):
                fact["unit"] = "tonnes"
                
        merged_facts = extractor.merge_and_normalize(text_facts, table_facts)
        print(f"Merged Facts: {json.dumps(merged_facts, indent=2)}")
        
        # 5. Evaluation
        print("\n--- Phase 4: Evaluation ---")
        eval_result = evaluate_run(merged_facts, [])
        print(f"Evaluation: {eval_result}")
        print("\nTest completed successfully!")

if __name__ == "__main__":
    main()
