import json
import networkx as nx
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import argparse

def load_question_bank(bank_path="eval_engine/question_bank.json"):
    with open(bank_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_metrics_from_graph(graph):
    """Extract all Standard and Specific ESG Metric nodes and their associated values/units."""
    metrics_data = []
    
    # Process Standard Metrics first as they are our best entry points
    for u, d in graph.nodes(data=True):
        if d.get("label") == "Standard ESG Metric":
            std_name = d.get("text", "")
            
            # Find specific metrics mapped to this standard node
            for specific_id, _, edge_data in graph.in_edges(u, data=True):
                if edge_data.get("relation") == "MAPPED_TO":
                    spec_node = graph.nodes[specific_id]
                    spec_name = spec_node.get("text", "")
                    
                    # Find values for this specific metric
                    values = []
                    for _, val_id, m_edge in graph.out_edges(specific_id, data=True):
                        if m_edge.get("relation") == "MEASURES":
                            val_node = graph.nodes[val_id]
                            val_text = val_node.get("text", "")
                            
                            # Find unit for this value
                            unit_text = ""
                            for _, unit_id, u_edge in graph.out_edges(val_id, data=True):
                                if u_edge.get("relation") == "has_unit":
                                    unit_text = graph.nodes[unit_id].get("text", "")
                            
                            values.append({
                                "value": val_text,
                                "unit": unit_text,
                                "specific_metric": spec_name
                            })
                    
                    if values:
                        metrics_data.append({
                            "id": u,
                            "text": std_name,
                            "values": values
                        })
            
    # Also include ESG Metrics that aren't mapped but might be relevant
    for u, d in graph.nodes(data=True):
        if d.get("label") == "ESG Metric":
            # If already mapped, skip
            if any(d.get("relation") == "MAPPED_TO" for _, _, d in graph.in_edges(u, data=True)):
                continue
                
            metric_text = d.get("text", "")
            values = []
            for _, val_id, m_edge in graph.out_edges(u, data=True):
                if m_edge.get("relation") == "MEASURES":
                    val_node = graph.nodes[val_id]
                    val_text = val_node.get("text", "")
                    unit_text = ""
                    for _, unit_id, u_edge in graph.out_edges(val_id, data=True):
                        if u_edge.get("relation") == "has_unit":
                            unit_text = graph.nodes[unit_id].get("text", "")
                    
                    values.append({
                        "value": val_text,
                        "unit": unit_text,
                        "specific_metric": metric_text
                    })
            
            if values:
                metrics_data.append({
                    "id": u,
                    "text": metric_text,
                    "values": values
                })
            
    return metrics_data

def evaluate_graph(graph_path, bank_path="eval_engine/question_bank.json"):
    if not Path(graph_path).exists():
        print(f"Error: Graph not found at {graph_path}")
        return

    print(f"Loading graph from {graph_path}...")
    G = nx.read_graphml(graph_path)
    
    print("Loading question bank...")
    questions = load_question_bank(bank_path)
    
    print("Extracting metrics from graph...")
    graph_metrics = extract_metrics_from_graph(G)
    
    if not graph_metrics:
        print("No ESG Metrics found in the graph.")
        return
        
    # Prepare text for TF-IDF matching
    corpus = [m["text"] for m in graph_metrics]
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(corpus)
    
    print("\n" + "="*100)
    print(f"{'EVALUATION ENGINE RESULTS':^100}")
    print("="*100 + "\n")
    
    success_count = 0
    
    for q in questions:
        print(f"Standard Question: {q['standard_question']}")
        print(f"Category: {q['category']} | Topic: {q['topic']}")
        
        # Build query from standard question and keywords
        query_text = q['standard_question'] + " " + " ".join(q['keywords'])
        query_vec = vectorizer.transform([query_text])
        
        # Calculate similarity
        similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
        best_match_idx = similarities.argmax()
        best_score = similarities[best_match_idx]
        
        if best_score > 0.15:  # Threshold for semantic match
            matched_metric = graph_metrics[best_match_idx]
            print(f"  [+] Graph Node Found: '{matched_metric['text']}' (Confidence: {best_score:.2f})")
            
            if matched_metric['values']:
                # Sort values: prioritize those containing "Total", "(Total)", or matching primary units
                def rank_val(v):
                    score = 0
                    spec = v.get('specific_metric', '').lower()
                    if "total" in spec: score += 10
                    if "(" in spec and ")" in spec: score += 5 # Likely a qualified header
                    if any(u in v['unit'].lower() for u in ['tco', 'gj', 'kilolitres', 'mt']): score += 3
                    return score

                sorted_vals = sorted(matched_metric['values'], key=rank_val, reverse=True)
                
                # Deduplicate and show top answers
                seen_answers = set()
                displayed_count = 0
                for val in sorted_vals:
                    ans = f"{val['value']} {val['unit']}".strip()
                    if ans in seen_answers: continue
                    seen_answers.add(ans)
                    
                    spec = f" (via '{val['specific_metric']}')" if val.get('specific_metric') else ""
                    print(f"      -> Extracted Answer: {ans}{spec}")
                    displayed_count += 1
                    if displayed_count >= 5: # Limit noise to top 5 most relevant
                        break
                        
                success_count += 1
            else:
                print("      -> [-] Node exists but has no linked Quantitative Values.")
        else:
            print(f"  [X] No semantic match found in graph. (Best score: {best_score:.2f})")
            
        print("-" * 100)
        
    print(f"\nSCORE: The graph successfully answered {success_count} out of {len(questions)} standard ESG questions ({(success_count/len(questions))*100:.1f}%).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a graph against standard ESG questions.")
    parser.add_argument("graph_path", help="Path to the graphml file")
    args = parser.parse_args()
    
    evaluate_graph(args.graph_path)
