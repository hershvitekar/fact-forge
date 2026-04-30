import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Set
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx


# ── Label groups for fuzzy dedup scope ────────────────────────────────────────
# Only merge nodes within the same group — never merge a Company with a Metric
LABEL_GROUPS = {
    "env":  {"ESG Metric", "Sustainability Framework"},
    "quant": {"Quantitative Value", "Unit of Measure"},
    "org":  {"Company", "Person", "Partnership", "Platform", "Internal Tool", "Internal Program"},
    "time": {"Reporting Year"},
    "policy": {"Policy Document"},
}

FUZZY_THRESHOLD = 0.72   # Jaccard/sequence similarity cutoff for merging


def _label_group(label: str) -> str:
    """Return the group key for a given label, or the label itself if unknown."""
    for group, labels in LABEL_GROUPS.items():
        if label in labels:
            return group
    return label  # treat unknown labels as their own singleton group


def _token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on lowercase word-token sets."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio on lowercased strings (handles substrings well)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _similarity(a: str, b: str) -> float:
    """Combined similarity: max of Jaccard and sequence ratio."""
    return max(_token_jaccard(a, b), _sequence_similarity(a, b))


def deduplicate_entities(entities: List[Dict], main_company: str = None) -> List[Dict]:
    """
    Deduplicate entities using fuzzy similarity within label groups.

    Strategy:
    1. Exact (text, label) dedup first (fast path).
    2. Main Company Alias merging: Force-merge "The Company", "Boeing", etc.
    3. Within each label group, pairwise similarity check.
    """
    if not entities:
        return entities

    logging.info("Deduplicating %d entities (fuzzy threshold=%.2f)", len(entities), FUZZY_THRESHOLD)

    # ── Step 1: Exact match dedup ──────────────────────────────────────────────
    seen_exact: dict = {}
    
    # Generic aliases for the main subject of the report
    SELF_ALIASES = {"the company", "the group", "our operations", "our business", "the firm", "the organization"}
    if main_company:
        SELF_ALIASES.add(main_company.lower().strip())

    for ent in entities:
        text_lower = ent["text"].lower().strip()
        label = ent.get("label", "")
        
        # Force-alias mapping: if it's a "Company" and matches a self-alias, use main_company text
        if label == "Company" and main_company and text_lower in SELF_ALIASES:
            key_text = main_company.lower().strip()
            ent["text"] = main_company # update for downstream
        else:
            key_text = text_lower

        key = (key_text, label)
        if key not in seen_exact or ent.get("score", 0) > seen_exact[key].get("score", 0):
            seen_exact[key] = ent
            
    candidates = list(seen_exact.values())

    # ── Step 2: Fuzzy dedup within label groups ────────────────────────────────
    # Group by label group
    groups: dict[str, List[Dict]] = {}
    for ent in candidates:
        g = _label_group(ent.get("label", "unknown"))
        groups.setdefault(g, []).append(ent)

    survivors: List[Dict] = []
    for group_name, group_ents in groups.items():
        # Skip groups that don't benefit from fuzzy merge (units, time, quant)
        if group_name in ("quant", "time", "unit"):
            survivors.extend(group_ents)
            continue

        # Greedy merge: iterate and mark duplicates
        merged = [True] * len(group_ents)  # True = still alive
        for i in range(len(group_ents)):
            if not merged[i]:
                continue
            for j in range(i + 1, len(group_ents)):
                if not merged[j]:
                    continue
                sim = _similarity(group_ents[i]["text"], group_ents[j]["text"])
                if sim >= FUZZY_THRESHOLD:
                    # Keep the one with higher score
                    if group_ents[j].get("score", 0) > group_ents[i].get("score", 0):
                        merged[i] = False  # i gets replaced by j
                        break             # i is gone; stop inner loop
                    else:
                        merged[j] = False  # j is a duplicate of i

        survivors.extend([e for e, alive in zip(group_ents, merged) if alive])

    logging.info("Dedup complete: %d → %d entities", len(entities), len(survivors))
    return survivors


# ── Graph-Based Entity Resolution (ER) ────────────────────────────────────────

def resolve_graph_entities(graph: nx.DiGraph):
    """
    Perform Entity Resolution on the assembled graph (Phase 1 & 2).
    1. Identify clusters using Cosine Similarity and SUBSIDIARY_OF rules.
    2. Collapse clusters into canonical nodes (shortest name).
    3. Migrate edges and merge attributes.
    """
    nodes = list(graph.nodes(data=True))
    if not nodes:
        return graph

    logging.info("Starting Graph-Based Entity Resolution (ER)...")
    initial_node_count = graph.number_of_nodes()
    initial_edge_count = graph.number_of_edges()

    # ── Phase 1: Cluster Identification ──────────────────────────────────────
    # Group by label to avoid merging across types
    by_label = {}
    for n, d in nodes:
        label = d.get("label", "Unknown")
        by_label.setdefault(label, []).append((n, d))

    clusters = []
    processed_nodes = set()

    for label, group in by_label.items():
        if label in ("Quantitative Value", "Reporting Year", "Unit of Measure"):
            continue # Skip these for now as per usual ESG logic

        # 1. Cosine Similarity Cluster
        texts = [d.get("text", "") or str(n) for n, d in group]
        if len(texts) > 1:
            try:
                vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
                tfidf_matrix = vectorizer.fit_transform(texts)
                cosine_sim = cosine_similarity(tfidf_matrix)

                for i in range(len(group)):
                    if group[i][0] in processed_nodes:
                        continue
                    
                    current_cluster = {group[i][0]}
                    for j in range(i + 1, len(group)):
                        if group[j][0] in processed_nodes:
                            continue
                        
                        # Rule 1: Cosine Similarity > 0.85
                        if cosine_sim[i, j] > 0.85:
                            current_cluster.add(group[j][0])
                    
                    if len(current_cluster) > 1:
                        clusters.append(current_cluster)
                        processed_nodes.update(current_cluster)
            except Exception as e:
                logging.warning("Error during TF-IDF vectorization: %s", e)

    # 2. SUBSIDIARY_OF Rule for Companies
    for src, tgt, data in list(graph.edges(data=True)):
        if data.get("relation") == "SUBSIDIARY_OF":
            if src in processed_nodes or tgt in processed_nodes:
                continue
            
            # Check for significant keyword overlap
            sim = _similarity(graph.nodes[src].get("text", ""), graph.nodes[tgt].get("text", ""))
            if sim > 0.6: # Relaxed threshold for hierarchy-based merging
                clusters.append({src, tgt})
                processed_nodes.update({src, tgt})

    # ── Phase 2: Collapsing Logic ─────────────────────────────────────────────
    for cluster in clusters:
        # Select canonical: shortest recognizable name
        nodes_in_cluster = [(n, graph.nodes[n]) for n in cluster]
        # Filter out empty or too short names if possible
        canonical_node_id, canonical_data = min(nodes_in_cluster, key=lambda x: len(x[1].get("text", "Unknown") or str(x[0])))

        # Remaining nodes to collapse
        others = [n for n in cluster if n != canonical_node_id]
        
        for other_node_id in others:
            # 1. Attribute Merge: Context fields
            old_ctx = graph.nodes[other_node_id].get("context", "")
            new_ctx = graph.nodes[canonical_node_id].get("context", "")
            if old_ctx and old_ctx not in new_ctx:
                graph.nodes[canonical_node_id]["context"] = (new_ctx + " | " + old_ctx).strip(" | ")

            # 2. Edge Migration: Incoming
            for s, _, data in list(graph.in_edges(other_node_id, data=True)):
                if s == canonical_node_id or s == other_node_id: continue
                if not graph.has_edge(s, canonical_node_id):
                    graph.add_edge(s, canonical_node_id, **data)
            
            # 3. Edge Migration: Outgoing
            for _, t, data in list(graph.out_edges(other_node_id, data=True)):
                if t == canonical_node_id or t == other_node_id: continue
                if not graph.has_edge(canonical_node_id, t):
                    graph.add_edge(canonical_node_id, t, **data)
            
            # 4. Phase 3: Cleanup - Delete redundant node
            graph.remove_node(other_node_id)

    final_node_count = graph.number_of_nodes()
    final_edge_count = graph.number_of_edges()
    
    # Recalculate density
    density = final_edge_count / final_node_count if final_node_count > 0 else 0
    
    logging.info("ER Complete: Merged %d clusters. Nodes: %d -> %d. Density: %.4f", 
                 len(clusters), initial_node_count, final_node_count, density)
    
    return graph
