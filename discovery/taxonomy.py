import logging
import json
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

def discover_taxonomy(document, prescan, models=None):
    """
    Discovers ESG taxonomy signals by mapping document headers to 
    global regulatory standards using semantic embeddings.
    """
    logging.info("Discovering regulatory taxonomy via Semantic Mapping")
    
    scaffold = prescan.get("scaffold", [])
    if not scaffold or models is None or models.embedder is None:
        logging.warning("Insufficient data or models for semantic discovery. Using baseline.")
        return {"categories": [], "sections": [], "regulatory_map": {}}

    # 1. Load Global Question Bank
    bank_path = Path("eval_engine/global_question_bank.json")
    if not bank_path.exists():
        logging.error("Global question bank missing!")
        return {"categories": [], "sections": [], "regulatory_map": {}}

    with open(bank_path, 'r', encoding='utf-8') as f:
        bank_data = json.load(f)
        questions = bank_data.get("questions", [])

    # 2. Encode Questions (Standard Indicators)
    question_texts = [q["standard_question"] for q in questions]
    question_embeddings = models.embedder.encode(question_texts)
    
    # 3. Encode Scaffold (Report Headers)
    scaffold_texts = [item["text"][:1000] for item in scaffold]
    scaffold_embeddings = models.embedder.encode(scaffold_texts)

    # 4. Perform Similarity Matching
    # (Scaffold x Questions)
    similarities = cosine_similarity(scaffold_embeddings, question_embeddings)
    
    regulatory_map = {} # Standard_ID -> List of (page, score, context)
    
    # Threshold for a "Regulatory Anchor"
    # Lowered from 0.55 to 0.52 to improve recall on dense/noisy HUL headers
    THRESHOLD = 0.52 
    
    for q_idx, question in enumerate(questions):
        q_id = question["id"]
        # Find best scaffold matches for this specific regulatory indicator
        q_sims = similarities[:, q_idx]
        best_scaffold_indices = np.where(q_sims > THRESHOLD)[0]
        
        anchors = []
        for s_idx in best_scaffold_indices:
            item = scaffold[s_idx]
            text = item["text"]
            
            # STRICT FILTER: Only structural headers are anchors. 
            # Narrative sentences (long text without header markers) are rejected.
            is_narrative = len(text.split()) > 20 and not text.startswith('#')
            if item.get("type") == "heading" and not is_narrative:
                anchors.append({
                    "page": item["page"],
                    "score": float(q_sims[s_idx]),
                    "context": text
                })
        
        if anchors:
            # Sort anchors by score
            anchors.sort(key=lambda x: x["score"], reverse=True)
            regulatory_map[q_id] = anchors

    # 5. Determine high-level categories found
    found_cats = set()
    for q_id in regulatory_map:
        # Infer category from ID prefix (ENV_, SOC_, GOV_)
        if q_id.startswith("ENV"): found_cats.add("environment")
        elif q_id.startswith("SOC"): found_cats.add("social")
        elif q_id.startswith("GOV"): found_cats.add("governance")

    logging.info("Mapped %d regulatory indicators to document structure", len(regulatory_map))
    
    return {
        "categories": list(found_cats),
        "regulatory_map": regulatory_map,
        "sections": scaffold # Preserve scaffold for downstream use
    }
