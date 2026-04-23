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
    Export the knowledge graph into multiple formats:
      - observations.json   (MetricObservation nodes)
      - observations.csv    (same, as DataFrame)
      - nodes.csv           (all nodes)
      - edges.csv           (all edges)
      - graph_quality.json  (Task 8: health metrics + grade)
    """
    logging.info("Exporting KG to structured formats")
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # ── 1. Observations ────────────────────────────────────────────────────────
    observations = []
    for n, d in graph.nodes(data=True):
        if d.get("type") == "observation":
            observations.append(d)

    with open(output_path / "observations.json", "w", encoding="utf-8") as f:
        json.dump(observations, f, indent=2)

    if observations:
        pd.DataFrame(observations).to_csv(
            output_path / "observations.csv", index=False
        )
        logging.info("Exported %d observations to CSV", len(observations))
    else:
        logging.warning("No observations found — observations.csv will be empty")
        # Write header-only CSV so downstream tools don't break
        pd.DataFrame(columns=["text", "label", "value", "year", "unit", "type", "centrality"]).to_csv(
            output_path / "observations.csv", index=False
        )

    # ── 2. All Nodes ──────────────────────────────────────────────────────────
    nodes = []
    for n, d in graph.nodes(data=True):
        nodes.append({"id": n, **d})
    pd.DataFrame(nodes).to_csv(output_path / "nodes.csv", index=False)
    logging.info("Exported %d nodes to nodes.csv", len(nodes))

    # ── 3. All Edges ──────────────────────────────────────────────────────────
    edges = []
    for u, v, d in graph.edges(data=True):
        edges.append({"source": u, "target": v, **d})
    pd.DataFrame(edges).to_csv(output_path / "edges.csv", index=False)
    logging.info("Exported %d edges to edges.csv", len(edges))

    # ── 4. Task 8: Quality Report ─────────────────────────────────────────────
    export_quality_report(graph, output_path)
