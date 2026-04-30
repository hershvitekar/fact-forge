import networkx as nx
import json
from pathlib import Path

def generate_graph_summary(graph_path):
    """
    Summarizes the graph facts and trends for AI analysis.
    """
    if not Path(graph_path).exists():
        return "Graph not found."

    G = nx.read_graphml(graph_path)
    summary = {
        "metrics": [],
        "targets": [],
        "anomalies_detected": []
    }

    # 1. Extract Metrics & Years
    metrics = {}
    for u, d in G.nodes(data=True):
        if d.get("type") == "value":
            # Find the metric name and year for this value
            metric_name = "Unknown"
            year = "Unknown"
            unit = ""
            
            for m_id, _, edge_data in G.in_edges(u, data=True):
                if edge_data.get("relation") == "MEASURES":
                    metric_name = G.nodes[m_id].get("text", "")
            
            for _, y_id, edge_data in G.out_edges(u, data=True):
                if edge_data.get("relation") == "reported_at":
                    year = G.nodes[y_id].get("text", "")
                if edge_data.get("relation") == "has_unit":
                    unit = G.nodes[y_id].get("text", "")

            if metric_name not in metrics: metrics[metric_name] = {}
            metrics[metric_name][year] = f"{d.get('text')} {unit}".strip()

    # 2. Extract Targets
    for u, d in G.nodes(data=True):
        if d.get("type") == "target":
            summary["targets"].append({
                "description": d.get("text"),
                "year": d.get("year"),
                "type": d.get("target_type")
            })

    # 3. Simple Heuristic Anomaly: Year-over-Year Spikes (>20%)
    for metric, years in metrics.items():
        if "2025" in years and "2024" in years:
            try:
                v25 = float(years["2025"].split()[0])
                v24 = float(years["2024"].split()[0])
                if v24 != 0:
                    delta = (v25 - v24) / v24
                    if abs(delta) > 0.2:
                        summary["anomalies_detected"].append(
                            f"Significant change in {metric}: {v24} -> {v25} ({delta:+.1%})"
                        )
            except:
                pass
        
        summary["metrics"].append({"name": metric, "values": years})

    return summary

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = generate_graph_summary(sys.argv[1])
        print(json.dumps(res, indent=2))
