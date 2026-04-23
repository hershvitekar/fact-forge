import logging
import config

def extract_relations(document, glirel_model, sentences, entities):
    """Extract relations from overlapping paragraphs (3-5 sentences)."""
    logging.info("Extracting relations from %d sentences at paragraph granularity", len(sentences))
    full_text = document.get("text", "")
    relations = []
    labels = list(config.ESG_RELATION_LABELS.keys())
    
    # Use sliding window of sentences to form paragraphs
    window_size = config.RELATION_PARA_SENTENCES
    stride = 2 # Overlap sentences for better coverage
    
    current_global_offset = 0
    
    total_windows = (len(sentences) // stride) + 1
    
    for i in range(0, len(sentences), stride):
        window_num = (i // stride) + 1
        if window_num % 5 == 0 or window_num == 1:
            logging.info("--> GLiREL Extraction: Window %d of ~%d", window_num, total_windows)
        
        batch_sents = sentences[i : i + window_size]
        if not batch_sents:
            break
            
        para_text = " ".join(batch_sents)
        para_start_in_doc = full_text.find(batch_sents[0], current_global_offset)
        if para_start_in_doc == -1:
            para_start_in_doc = current_global_offset
        
        para_end_in_doc = para_start_in_doc + len(para_text)
        
        # Filter entities that are within this paragraph
        para_entities = [
            ent for ent in entities 
            if ent["start"] >= para_start_in_doc and ent["end"] <= para_end_in_doc
        ]
        
        if len(para_entities) < 2:
            continue
            
        # Prepare GLiREL format: [start_char, end_char, label, text]
        # GLiREL predict_relations handles tokenization internally if text is a string
        # but here we'll provide tokens and ner relative to the paragraph
        # Robust tokenization and entity mapping
        para_tokens = []
        char_to_token = {}
        
        # Build a map of character positions to token indices
        current_char = 0
        for token in para_text.split():
            start_idx = para_text.find(token, current_char)
            token_idx = len(para_tokens)
            para_tokens.append(token)
            
            # Map every character in this token to this token_idx
            for c in range(start_idx, start_idx + len(token)):
                char_to_token[c] = token_idx
            current_char = start_idx + len(token)

        para_ner = []
        for ent in para_entities:
            rel_start = ent["start"] - para_start_in_doc
            rel_end = ent["end"] - para_start_in_doc
            
            # Find which tokens cover this span
            # We look for the first and last character of the entity in our map
            start_token = char_to_token.get(rel_start)
            # end_token is exclusive in GLiREL
            end_token_incl = char_to_token.get(rel_end - 1)
            
            if start_token is not None and end_token_incl is not None:
                para_ner.append([start_token, end_token_incl + 1, ent["label"], ent["text"]])
            else:
                logging.debug("Could not map entity '%s' to tokens in paragraph", ent["text"])

        if not para_ner:
            continue

        try:
            # Using text=para_tokens as discovered in model.py analysis
            raw_relations = glirel_model.predict_relations(
                text=para_tokens,
                labels=labels,
                threshold=config.GLIREL_CONFIDENCE,
                ner=para_ner,
                top_k=1
            )
            for rel in raw_relations:
                head = rel["head_text"]
                tail = rel["tail_text"]
                
                # If GLiREL returns tokens as a list, join them into a string
                if isinstance(head, list):
                    head = " ".join(head)
                if isinstance(tail, list):
                    tail = " ".join(tail)
                    
                relations.append({
                    "relation": rel["label"],
                    "head": head,
                    "tail": tail,
                    "score": rel["score"]
                })
        except Exception as e:
            logging.debug("GLiREL paragraph extraction failed: %s", e)

        # Advance global offset for next find
        current_global_offset = para_start_in_doc + len(batch_sents[0])

    logging.info("Extracted %d raw relations from GLiREL", len(relations))
    return relations

