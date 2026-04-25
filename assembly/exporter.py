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
        nodes_by_label.setdefault(label, []).append({"id": n, **d})

    # 2. Group edges by Relation
    edges_by_relation = {}
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation", "UNKNOWN_RELATION").replace(" ", "_")
        edges_by_relation.setdefault(rel, []).append({"source": u, "target": v, **d})

    # Export Nodes
    for label, nodes in nodes_by_label.items():
        df = pd.DataFrame(nodes)
        csv_path = output_path / f"nodes_{label}.csv"
        df.to_csv(csv_path, index=False)
        logging.info("Exported %d %s nodes", len(nodes), label)

    # Export Edges
    for rel, edges in edges_by_relation.items():
        df = pd.DataFrame(edges)
        csv_path = output_path / f"edges_{rel}.csv"
        df.to_csv(csv_path, index=False)
        logging.info("Exported %d %s edges", len(edges), rel)

    # 3. Quality Report
    export_quality_report(graph, output_path)
