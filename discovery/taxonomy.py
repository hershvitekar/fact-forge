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
    # Lowered from 0.52 to 0.45 to significantly improve recall
    THRESHOLD = 0.45 
    
    # ── Category Keywords for structural fallback ─────────────────────────────
    PILLAR_KEYWORDS = {
        "ENV": ["environmental", "principle 6", "climate", "water", "waste", "energy", "emissions"],
        "SOC": ["social", "principle 3", "principle 8", "workforce", "employees", "safety", "communities", "diversity"],
        "GOV": ["governance", "principle 1", "board", "directors", "ethics", "compliance"]
    }

    for q_idx, question in enumerate(questions):
        q_id = question["id"]
        pillar_code = q_id.split('_')[0] if '_' in q_id else ""
        pillar_kws = PILLAR_KEYWORDS.get(pillar_code, [])

        # Find best scaffold matches for this specific regulatory indicator
        q_sims = similarities[:, q_idx]
        best_scaffold_indices = list(np.where(q_sims > THRESHOLD)[0])
        
        # KEYWORD FALLBACK: If embedding failed, look for pillar-specific headers
        if not best_scaffold_indices:
            for s_idx, item in enumerate(scaffold):
                header_text = item["text"].lower()
                if any(kw in header_text for kw in pillar_kws):
                    # If the header matches the pillar, it's a valid anchor
                    best_scaffold_indices.append(s_idx)

        anchors = []
        for s_idx in best_scaffold_indices:
            item = scaffold[s_idx]
            text = item["text"]
            
            # Narrative filter (slightly relaxed: headers can be up to 30 words)
            is_narrative = len(text.split()) > 30 and not text.startswith('#')
            if not is_narrative:
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
