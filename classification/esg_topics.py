import logging

def classify_esg_topics(document, models):
    """Classify ESG topic signals using ESGBERT and other models."""
    logging.info("Classifying ESG topics")
    text = document.get("text", "")
    
    # We'll split the text into segments (e.g., first 512 characters or sentences)
    # For a full implementation, we might want to sample across the document.
    sample_text = text[:1000] # Use a sample for efficiency
    
    results = {}
    
    if models.esg_env:
        env_res = models.esg_env(sample_text)
        # Assuming the pipeline returns a list of labels/scores
        results["environment"] = env_res[0]["score"] if env_res else 0.0
        
    if models.esg_social:
        soc_res = models.esg_social(sample_text)
        results["social"] = soc_res[0]["score"] if soc_res else 0.0
        
    if models.esg_gov:
        gov_res = models.esg_gov(sample_text)
        results["governance"] = gov_res[0]["score"] if gov_res else 0.0
        
    return results
