import logging
import re

def clean_text_for_ner(text: str) -> str:
    """
    Strips Markdown tables and excessive punctuation noise to prevent GLiNER 
    from processing non-sentential table data.
    """
    # Remove markdown table rows (lines starting and ending with | or containing |---|)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        # Regex to detect lines that are primarily table borders or cells
        if re.search(r'\|[-:| ]+\|', line) or (line.count('|') > 1):
            continue
        clean_lines.append(line)
    
    return "\n".join(clean_lines)

def is_heading(sent_text: str):
    """Heuristic to detect if a sentence is a heading."""
    text = sent_text.strip()
    
    # 0. Skip table borders (|---| or ----)
    if re.match(r'^[|\-\s:]+$', text):
        return False
        
    # 1. Starts with Markdown header
    if text.startswith('#'):
        return True
    # 2. Short and capitalized (e.g., "PRINCIPLE 6")
    if len(text) < 100 and (text.isupper() or re.match(r'^(?:Principle|Section|Chapter|FY)\b', text, re.I)):
        return True
    # 3. Numeric list start
    if re.match(r'^\d+\.\s+[A-Z]', text):
        return True
    return False

def run_spacy_prescan(document, nlp):
    """
    Perform a structural spaCy pass over the document.
    Returns entities, sentences, and a 'scaffold' of structural headers.
    """
    pages = document.get("pages", [])
    logging.info("Running spaCy structural prescan on %d pages", len(pages))
    
    all_sentences = []
    all_entities = []
    scaffold = [] # List of {"text": str, "page": int, "type": str}
    
    # Process pages individually to maintain page tracking
    for p_idx, page in enumerate(pages):
        page_text = page.get("text", "")
        if not page_text:
            continue
            
        cleaned_text = clean_text_for_ner(page_text)
        doc = nlp(cleaned_text)
        
        for sent in doc.sents:
            sent_text = sent.text.strip()
            if not sent_text:
                continue
                
            all_sentences.append(sent_text)
            
            # Identify scaffold elements
            if is_heading(sent_text):
                # Extra check: Headings shouldn't be too long unless they start with #
                if len(sent_text.split()) < 15 or sent_text.startswith('#'):
                    scaffold.append({
                        "text": sent_text,
                        "page": p_idx + 1,
                        "type": "heading"
                    })
            elif "table" in sent_text.lower() and len(sent_text) < 100:
                # Ensure it looks like a table reference (e.g., "Table 1:", "Refer to table below")
                if any(x in sent_text.lower() for x in [":", "below", "following", "details"]):
                    scaffold.append({
                        "text": sent_text,
                        "page": p_idx + 1,
                        "type": "table_anchor"
                    })
                
        # Collect entities
        for ent in doc.ents:
            all_entities.append({
                "text": ent.text,
                "label": ent.label_,
                "page": p_idx + 1,
                "start": ent.start_char
            })
            
    return {
        "entities": all_entities,
        "sentences": all_sentences,
        "scaffold": scaffold
    }
