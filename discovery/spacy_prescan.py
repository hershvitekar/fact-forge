import logging


def run_spacy_prescan(document, nlp):
    """Perform a quick spaCy pass over the document page-by-page."""
    logging.info("Running spaCy prescan on %d pages", len(document.get("pages", [])))
    
    all_sentences = []
    all_entities = []
    
    # Process pages to handle large documents and maintain section-like granularity
    page_texts = [p["text"] for p in document.get("pages", [])]
    for doc in nlp.pipe(page_texts, batch_size=5):
        all_sentences.extend([sent.text for sent in doc.sents])
        all_entities.extend([(ent.text, ent.label_) for ent in doc.ents])
        
    return {
        "entities": all_entities,
        "sentences": all_sentences,
    }

