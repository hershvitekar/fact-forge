import logging
import config

def rank_sections(document, entities):
    """Rank sections by their density of ESG entities."""
    logging.info("Ranking sections by ESG density")
    
    pages = document.get("pages", [])
    page_scores = []
    
    for i, page in enumerate(pages):
        page_text = page["text"]
        page_entities = [e for e in entities if e["text"] in page_text]
        score = len(page_entities) / (len(page_text) / 1000 + 1) # Entities per 1000 chars
        page_scores.append({"index": i, "score": score, "page_number": page.get("page_number", i+1)})
        
    # Sort by score descending
    page_scores.sort(key=lambda x: x["score"], reverse=True)
    
    # Filter by cutoff percentile
    cutoff_idx = int(len(page_scores) * (config.SECTION_RANK_CUTOFF_PERCENTILE / 100))
    ranked_sections = page_scores[:max(1, cutoff_idx)]
    
    return ranked_sections
