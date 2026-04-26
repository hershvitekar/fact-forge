import json
import logging
import networkx as nx
import pandas as pd
from pathlib import Path


# ── Task 8: Graph quality grading ─────────────────────────────────────────────

def _compute_grade(density: float, isolated_ratio: float) -> str:
    """Assign an A–D letter grade based on graph density and isolation rate."""
    if density >= 0.010 and isolated_ratio <= 0.25:
        return "A"
    if density >= 0.004 and isolated_ratio <= 0.40:
        return "B"
    if density >= 0.001 and isolated_ratio <= 0.65:
        return "C"
    return "D"


def export_quality_report(graph: nx.DiGraph, output_dir: Path) -> dict:
    """
    Compute and persist graph health metrics to graph_quality.json.

    Metrics:
      - nodes, edges, density
      - isolated nodes count and percentage
      - weakly connected components
      - node type distribution
      - letter grade (A–D)
    """
    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()
    density = nx.density(graph) if n_nodes > 1 else 0.0

    isolated     = list(nx.isolates(graph))
    n_isolated   = len(isolated)
    isolated_pct = round(n_isolated / n_nodes * 100, 1) if n_nodes else 0.0

    # Weakly connected components (treats directed as undirected)
    components = nx.number_weakly_connected_components(graph) if n_nodes else 0

    # Node type / label distribution
    node_type_counts: dict[str, int] = {}
    for _, d in graph.nodes(data=True):
        label = d.get("label", "Unknown")
        node_type_counts[label] = node_type_counts.get(label, 0) + 1

    grade = _compute_grade(density, n_isolated / n_nodes if n_nodes else 1.0)

    report = {
        "nodes":                       n_nodes,
        "edges":                       n_edges,
        "density":                     round(density, 6),
        "isolated_nodes":              n_isolated,
        "isolated_pct":                isolated_pct,
        "weakly_connected_components": components,
        "node_type_distribution":      node_type_counts,
        "grade":                       grade,
    }

    quality_path = Path(output_dir) / "graph_quality.json"
    with open(quality_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logging.info(
        "Graph quality report: %d nodes, %d edges, density=%.4f, isolated=%.1f%%, grade=%s",
        n_nodes, n_edges, density, isolated_pct, grade,
    )
    return report


# ── Main export function ───────────────────────────────────────────────────────

def export_kg(graph: nx.DiGraph, output_dir) -> None:
    """
    Export the knowledge graph into Kùzu-compatible schema-separated formats:
      - nodes_{Label}.csv
      - edges_{Relation}.csv
      - graph_quality.json
    """
    logging.info("Exporting KG to Kùzu-compatible separated schema CSVs")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1. Group nodes by Label
    nodes_by_label = {}
    for n, d in graph.nodes(data=True):
        label = d.get("label", "Unknown").replace(" ", "_")
        # POLISH: Extract essential properties including context for narrative insights
        node_props = {
            "id": n,
            "text": d.get("text", ""),
            "topic": d.get("topic", ""),
            "page": d.get("page_number", 1),
            "context": d.get("context", "")
        }
        # Add numeric value for Quantitative Values
        if label == "Quantitative_Value":
            node_props["value_float"] = d.get("value_float", 0.0)

        nodes_by_label.setdefault(label, []).append(node_props)

    # 2. Group edges by Relation AND Node Types (Critical for Kùzu)
    # Kùzu Rel Tables are typed: FROM Table TO Table. 
    # We must separate them to avoid "Primary Key Not Found" errors.
    edges_by_type = {}
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation", "UNKNOWN_RELATION").replace(" ", "_")
        
        # Get labels of the nodes
        src_label = graph.nodes[u].get("label", "Unknown").replace(" ", "_")
        dst_label = graph.nodes[v].get("label", "Unknown").replace(" ", "_")
        
        # POLISH: Use TRIPLE UNDERSCORE to avoid confusion with table names like Unit_of_Measure
        type_key = f"{rel}___{src_label}___{dst_label}"
        
        edge_props = {
            "from": u,
            "to": v,
            "confidence": d.get("confidence", 1.0)
        }
        if "year" in d: edge_props["year"] = d["year"]
        if "unit" in d: edge_props["unit"] = d["unit"]

        edges_by_type.setdefault(type_key, []).append(edge_props)

    # Export Nodes
    for label, nodes in nodes_by_label.items():
        df = pd.DataFrame(nodes)
        csv_path = output_path / f"nodes_{label}.csv"
        df.to_csv(csv_path, index=False)
        logging.info("Exported %d %s nodes (cleaned)", len(nodes), label)

    # Export Edges (Typed)
    for type_key, edges in edges_by_type.items():
        df = pd.DataFrame(edges)
        csv_path = output_path / f"edges_{type_key}.csv"
        df.to_csv(csv_path, index=False)
        logging.info("Exported %d %s edges (typed)", len(edges), type_key)

    # 3. Quality Report
    export_quality_report(graph, output_path)
