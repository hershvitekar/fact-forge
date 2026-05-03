import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any

from llama_index.core import Document, VectorStoreIndex, StorageContext, load_index_from_storage, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from langsmith import traceable

from config import INDEX_STORAGE_PATH
from parsers.table_processor import extract_structured_facts

# Setup Embedding Model globally
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")


class DocumentIngestor:
    def __init__(self, index_storage_path=INDEX_STORAGE_PATH):
        self.index_storage_path = Path(index_storage_path)
        self.splitter = SentenceSplitter(chunk_size=800, chunk_overlap=100)

    @traceable(name="ingest_document")
    def ingest(self, markdown_path: str, doc_id: str) -> VectorStoreIndex:
        with open(markdown_path, 'r', encoding='utf-8') as f:
            text = f.read()

        doc = Document(text=text, doc_id=doc_id)
        
        nodes = self.splitter.get_nodes_from_documents([doc])
        
        for i, node in enumerate(nodes):
            node.metadata = {
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}_chunk_{i}",
                "page_number": None # Placeholder
            }
        
        index = VectorStoreIndex(nodes)
        
        persist_dir = self.index_storage_path / doc_id
        persist_dir.mkdir(parents=True, exist_ok=True)
        index.storage_context.persist(persist_dir=str(persist_dir))
        logging.info(f"Index persisted to {persist_dir}")
        return index


def run_gliner_glirel(text: str, doc_id: str, chunk_id: str) -> List[Dict[str, Any]]:
    """Mock NLP function for entity/relation extraction."""
    # In a real implementation, this would invoke the models from config.py
    return [{
        "metric": "Scope 1 Emissions",
        "value": "1000",
        "unit": "tonnes",
        "year": 2023,
        "source": "text",
        "doc_id": doc_id,
        "chunk_id": chunk_id
    }]


def standardize_unit(unit: str) -> str:
    if not unit:
        return unit
    unit_lower = unit.lower()
    if unit_lower in ["tonnes", "tco2e", "metric tonnes"]:
        return "MtCO2e"
    return unit


class ESGExtractor:
    def __init__(self, doc_id: str, index_storage_path=INDEX_STORAGE_PATH):
        self.doc_id = doc_id
        self.persist_dir = Path(index_storage_path) / doc_id
        
        if self.persist_dir.exists():
            storage_context = StorageContext.from_defaults(persist_dir=str(self.persist_dir))
            self.index = load_index_from_storage(storage_context)
        else:
            self.index = None

    @traceable(name="extract_from_text")
    def extract_from_text(self, query: str) -> List[Dict[str, Any]]:
        if not self.index:
            logging.warning(f"Index not found for {self.doc_id}.")
            return []
            
        retriever = self.index.as_retriever(similarity_top_k=5)
        nodes = retriever.retrieve(query)
        
        all_facts = []
        for node in nodes:
            doc_id = node.metadata.get("doc_id", self.doc_id)
            chunk_id = node.metadata.get("chunk_id", "unknown")
            text = node.get_content()
            facts = run_gliner_glirel(text, doc_id, chunk_id)
            all_facts.extend(facts)
        return all_facts

    @traceable(name="extract_from_tables")
    def extract_from_tables(self, tables_json_path: str) -> List[Dict[str, Any]]:
        if not Path(tables_json_path).exists():
            logging.warning(f"Tables JSON not found at {tables_json_path}.")
            return []
            
        with open(tables_json_path, 'r', encoding='utf-8') as f:
            tables_data = json.load(f)
            
        table_facts = []
        for table in tables_data:
            grid = table.get("data", {}).get("data", {}).get("grid", [])
            if not grid:
                continue
            
            structured_facts = extract_structured_facts(grid)
            
            for fact in structured_facts:
                fact["doc_id"] = self.doc_id
            
            table_facts.extend(structured_facts)
            
        return table_facts

    @traceable(name="merge_and_normalize")
    def merge_and_normalize(self, text_facts: List[Dict], table_facts: List[Dict]) -> List[Dict]:
        unique_facts = {}
        
        def _get_key(fact):
            return (str(fact.get("metric")).strip().lower(), fact.get("year"))

        for fact in table_facts:
            fact["unit"] = standardize_unit(fact.get("unit"))
            key = _get_key(fact)
            if key[0] and key[1]: 
                unique_facts[key] = fact
            
        for fact in text_facts:
            fact["unit"] = standardize_unit(fact.get("unit"))
            key = _get_key(fact)
            if key[0] and key[1] and key in unique_facts:
                continue # prioritize table fact
            elif key[0] and key[1]:
                unique_facts[key] = fact
                
        merged = list(unique_facts.values())
        
        for fact in table_facts + text_facts:
            key = _get_key(fact)
            if not (key[0] and key[1]):
                merged.append(fact)
                
        return merged

@traceable(name="evaluate_run")
def evaluate_run(extracted: list, gold: list) -> Dict[str, float]:
    """Placeholder for evaluation logic."""
    precision = 0.85
    recall = 0.75
    return {"precision": precision, "recall": recall}
