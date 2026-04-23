import logging
import config

def extract_entities(document, gliner_model, sentences):
    """Extract entities from sentences using GLiNER with sentence-level granularity."""
    logging.info("Extracting entities from %d sentences", len(sentences))
    labels = config.BASE_ESG_ENTITY_TYPES
    entities = []
    
    # 1. Heuristic for the "Anchor" Company (usually in the first few sentences or path)
    # In V2, we want to ensure everything is anchored to a company.
    source_name = document.get("source_path", "").split("/")[-1].split("-")[0]
    if source_name and len(source_name) > 2:
         # Add the company as a pseudo-entity found at the start of the doc
         entities.append({
             "text": source_name,
             "label": "Company",
             "score": 1.0,
             "start": 0,
             "end": len(source_name)
         })

    current_global_offset = 0
    full_text = document.get("text", "")
    
    # Process in batches for performance
    batch_size = config.ENTITY_BATCH_SIZE
    total_batches = (len(sentences) // batch_size) + 1
    
    for i in range(0, len(sentences), batch_size):
        batch_num = (i // batch_size) + 1
        logging.info("--> GLiNER Extraction: Batch %d of %d", batch_num, total_batches)
        batch = sentences[i : i + batch_size]
        # GLiNER batch_predict_entities returns a list of lists of entities
        batch_results = gliner_model.batch_predict_entities(batch, labels, threshold=config.GLINER_CONFIDENCE)
        
        for j, sentence_entities in enumerate(batch_results):
            sentence_text = batch[j]
            # Find the actual start of this sentence in the full text to align offsets
            sentence_start_in_doc = full_text.find(sentence_text, current_global_offset)
            if sentence_start_in_doc == -1:
                sentence_start_in_doc = current_global_offset
            
            for ent in sentence_entities:
                entities.append({
                    "text": ent["text"],
                    "label": ent["label"],
                    "score": ent["score"],
                    "start": sentence_start_in_doc + ent["start"],
                    "end": sentence_start_in_doc + ent["end"]
                })
            
            current_global_offset = sentence_start_in_doc + len(sentence_text)

    return entities
