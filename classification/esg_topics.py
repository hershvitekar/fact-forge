import logging

def chunk_text(text, size=1000, overlap=100):
    """Split text into overlapping chunks to ensure no signal is lost."""
    if len(text) <= size:
        return [text]
    chunks = []
    for i in range(0, len(text), size - overlap):
        chunks.append(text[i:i + size])
    return chunks

def classify_esg_topics(document, models, prescan=None):
    """
    Classify ESG topic signals using ESGBERT with a sliding window 
    to handle long structural blocks without data loss.
    """
    logging.info("Classifying ESG topics via Sliding Window Scaffold Scan")
    
    scaffold = prescan.get("scaffold", []) if prescan else []
    if not scaffold:
        text = document.get("text", "")
        scaffold = [{"text": text[:5000]}] # Larger sample if no scaffold
        
    topic_scores = {"environment": [], "social": [], "governance": []}
    
    for item in scaffold:
        full_text = item["text"]
        # Split into chunks to respect model limits (512 tokens / ~2000 chars)
        chunks = chunk_text(full_text)
        
        for chunk in chunks:
            # Environmental
            if models.esg_env:
                res = models.esg_env(chunk)
                if res: topic_scores["environment"].append(res[0]["score"])
            
            # Social
            if models.esg_social:
                res = models.esg_social(chunk)
                if res: topic_scores["social"].append(res[0]["score"])
                
            # Governance
            if models.esg_gov:
                res = models.esg_gov(chunk)
                if res: topic_scores["governance"].append(res[0]["score"])

    # Final aggregation
    final_results = {}
    for cat, scores in topic_scores.items():
        # We take the max signal found in any chunk/scaffold point 
        # to ensure the most relevant topic is highlighted
        final_results[cat] = max(scores) if scores else 0.0
            
    return final_results
