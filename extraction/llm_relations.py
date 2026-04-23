import logging
import json
from utils.llm_client import query_llm

def infer_complex_relations(document, relations, main_company=None):
    """
    V2.1: Full-Document Chunked Fact Builder.
    Processes the entire document in overlapping chunks to extract high-fidelity 
    ESG observations, targets, and events.
    """
    full_text = document.get("text", "")
    if not full_text:
        logging.warning("No text found in document for LLM inference")
        return relations

    # Chunking configuration
    CHUNK_SIZE = 4000
    OVERLAP = 500
    
    logging.info("Building structured facts with LLM over full document (%d chars)", len(full_text))
    
    # Calculate total expected chunks for logging
    total_chunks = (len(full_text) // (CHUNK_SIZE - OVERLAP)) + 1
    
    company_name = main_company if main_company else "the company"
    structured_facts = []
    
    # Iterate through the document in chunks
    start = 0
    chunk_count = 0
    while start < len(full_text):
        chunk_count += 1
        end = start + CHUNK_SIZE
        text_chunk = full_text[start:end]
        
        logging.info("--> LLM Fact Extraction: Chunk %d of ~%d", chunk_count, total_chunks)
        
        prompt = f"""
        You are an ESG Data Expert. Your task is to extract structured facts from the following report segment.
        All references to "we", "our", or "the company" in this text refer to: {company_name}.
        
        Focus on:
        1. MetricObservation: Specific numeric values for ESG metrics (emissions, energy, etc.)
        2. Target: Future commitments (Net Zero, reduction targets)
        3. Event: Significant changes or achievements (e.g., "reduced emissions by 15%")

        Format your output as a JSON list of objects. Each object must have a "type" field.
        
        SCHEMA EXAMPLES:
        {{
          "type": "MetricObservation",
          "company": "{company_name}",
          "metric": "Scope 1 Emissions",
          "value": 1.2,
          "unit": "tCO2e",
          "year": 2023,
          "confidence": 0.95
        }}
        {{
          "type": "Target",
          "company": "{company_name}",
          "target_type": "Net Zero",
          "target_year": 2030,
          "baseline_year": 2020
        }}
        {{
          "type": "Event",
          "company": "{company_name}",
          "event_type": "Reduction",
          "value": "18%",
          "year": 2023,
          "related_metric": "Emissions"
        }}

        TEXT SEGMENT:
        {text_chunk}

        JSON OUTPUT (List of objects):
        """
        
        response = query_llm(prompt)
        chunk_facts = _parse_llm_response(response)
        structured_facts.extend(chunk_facts)
        
        # Move start pointer forward by (CHUNK_SIZE - OVERLAP)
        start += (CHUNK_SIZE - OVERLAP)
        
        # Safety break if no progress
        if start >= len(full_text) or CHUNK_SIZE <= OVERLAP:
            break

    logging.info("Total structured facts extracted from %d chunks: %d", chunk_count, len(structured_facts))
    
    # Combine original relations with new full-doc facts
    return relations + structured_facts

def _parse_llm_response(response):
    """Helper to safely extract and parse JSON list from LLM response string."""
    if not response:
        return []
        
    try:
        content = response.strip()
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        start_idx = content.find("[")
        if start_idx != -1:
            bracket_count = 0
            end_idx = -1
            for i in range(start_idx, len(content)):
                if content[i] == "[":
                    bracket_count += 1
                elif content[i] == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_idx = i
                        break
            
            if end_idx != -1:
                json_str = content[start_idx:end_idx+1]
                return json.loads(json_str)
            else:
                json_str = content[start_idx:content.rfind("]")+1]
                return json.loads(json_str)
    except Exception as e:
        logging.debug("Partial failure parsing LLM chunk response: %s", e)
        
    return []
