import logging
import networkx as nx
import json
from .normalization import normalize_text, should_filter_entity, reclassify_entity_label


def build_graph(document, entities, relations, taxonomy, topics, quant_qual,
                relation_threshold=0.08, main_company=None):
    """
    Build V2 ESG Knowledge Graph with strictly typed nodes and structured facts.
    Improvements (Tasks 4 & 7):
      - Entity labels post-processed via reclassify_entity_label()
      - After all nodes are built, link_cooccurring_values() adds MEASURES edges
        between Quantitative Value nodes and same-page subject entities
    """
    logging.info("Building V2 graph from %d entities and %d relations/facts",
                 len(entities), len(relations))
    graph = nx.DiGraph()

    # Global metadata
    graph.graph["source"]         = document.get("source_path")
    graph.graph["document_title"] = document.get("source_path")
    graph.graph["page_count"]     = document.get("page_count", 0)
    graph.graph["topics"]         = json.dumps(topics)
    graph.graph["taxonomy"]       = json.dumps(taxonomy)

    # ── 1. Process Basic Entities (from GLiNER) ────────────────────────────────
    node_id_map = {}   # norm_text → node_id
    main_company_node = None
    norm_main_company = normalize_text(main_company) if main_company else None

    for i, entity in enumerate(entities):
        text = entity["text"]
        if should_filter_entity(text):
            continue

        raw_label = entity["label"]
        norm_text = normalize_text(text, label=raw_label)

        # Skip if we already added a node with this exact normalized text
        if norm_text in node_id_map:
            continue

        # ── Task 7: reclassify misidentified entity types ──────────────────────
        label = reclassify_entity_label(text, raw_label)

        node_id = f"node_{i}"
        node_id_map[norm_text] = node_id

        attrs = dict(
            text=norm_text,
            original_text=text,
            label=label,
            score=entity["score"],
            type="entity",
            centrality=entity.get("centrality", 0.0),
        )
        # Preserve page/context if present
        if entity.get("page_number") is not None:
            attrs["page_number"] = entity["page_number"]
        if entity.get("context"):
            attrs["context"] = entity["context"]

        graph.add_node(node_id, **attrs)

        if label == "Company" and not main_company_node:
            if not norm_main_company or norm_text == norm_main_company:
                main_company_node = node_id

    # ── 2. Process Relations and Structured Facts ──────────────────────────────
    for rel in relations:
        if not isinstance(rel, dict):
            continue

        rel_type = rel.get("type", "SimpleRelation")

        if rel_type == "MetricObservation":
            _handle_observation(graph, rel, main_company_node)
        elif rel_type == "Target":
            _handle_target(graph, rel, main_company_node)
        elif rel_type == "Event":
            _handle_event(graph, rel, main_company_node)
        else:
            _handle_simple_relation(graph, rel, node_id_map, relation_threshold)

    # NOTE: Co-occurrence value linking is deferred to AFTER enrichment
    # because page_number is not yet available at this stage.
    # Call link_after_enrichment(graph) from main.py after enrich_metadata().

    logging.info("Graph built: %d nodes, %d edges",
                 graph.number_of_nodes(), graph.number_of_edges())
    return graph


def link_after_enrichment(graph: nx.DiGraph) -> None:
    """
    Public entry point: add MEASURES edges using page co-occurrence.

    Must be called AFTER enrichment/metadata.py has populated page_number
    on entity nodes. Calling it earlier would find zero page numbers and
    silently produce no edges.
    """
    _link_cooccurring_values(graph)


# ── Structured fact handlers ───────────────────────────────────────────────────

def _handle_observation(graph, obs, company_node):
    """Create structured nodes for a MetricObservation."""
    metric_name = normalize_text(obs.get("metric", "Unknown Metric"), label="ESG Metric")
    value       = str(obs.get("value", ""))
    year_raw    = obs.get("year")
    year        = str(year_raw).strip() if year_raw is not None else ""
    if year.lower() == "none": year = ""
    unit        = normalize_text(obs.get("unit", ""), label="Unit of Measure")

    obs_id    = f"obs_{metric_name}_{year}".replace(" ", "_").lower()
    metric_id = f"met_{metric_name}".replace(" ", "_").lower()

    graph.add_node(metric_id, text=metric_name, label="ESG Metric", type="metric")
    graph.add_node(obs_id,
                   text=f"{value} {unit}".strip(),
                   label="MetricObservation",
                   value=value, year=year, unit=unit,
                   type="observation")

    graph.add_edge(metric_id, obs_id, relation="HAS_OBSERVATION")

    if company_node:
        graph.add_edge(company_node, metric_id, relation="REPORTS_METRIC")

    if year:
        year_id = f"year_{year}"
        graph.add_node(year_id, text=year, label="Reporting Year", type="time")
        graph.add_edge(obs_id, year_id, relation="REPORTED_AT")


def _handle_target(graph, target, company_node):
    """Create structured nodes for a Target."""
    target_type = target.get("target_type", "General Target")
    year_raw    = target.get("target_year")
    year        = str(year_raw).strip() if year_raw is not None else ""
    if year.lower() == "none": year = ""

    target_id = f"target_{target_type}_{year}".replace(" ", "_").lower()
    graph.add_node(target_id,
                   text=f"{target_type} ({year})",
                   label="Target",
                   target_type=target_type, year=year,
                   type="target")

    if company_node:
        graph.add_edge(company_node, target_id, relation="HAS_TARGET")


def _handle_event(graph, event, company_node):
    """Create structured nodes for an Event."""
    event_type = event.get("event_type", "General Event")
    metric     = event.get("metric", "")
    value      = event.get("value", "")
    unit       = event.get("unit", "")
    year_raw   = event.get("year")
    year       = str(year_raw).strip() if year_raw is not None else ""
    if year.lower() == "none": year = ""

    display_text = f"{metric} {event_type}: {value} {unit}".strip() if metric else f"{event_type}: {value} {unit}".strip()
    event_id     = f"event_{event_type}_{metric}_{year}".replace(" ", "_").lower()

    graph.add_node(event_id,
                   text=display_text,
                   label="Event",
                   event_type=event_type,
                   metric=metric,
                   value=value,
                   unit=unit,
                   year=year,
                   type="event")

    if company_node:
        graph.add_edge(company_node, event_id, relation="HAS_EVENT")


def _handle_simple_relation(graph, rel, node_id_map, threshold):
    """Create edge for a standard relation if above threshold."""
    if rel.get("score", 1.0) < threshold:
        return

    head = rel.get("head")
    tail = rel.get("tail")
    if not head or not tail:
        return

    # Handle if head or tail is a list (bug from previous logic)
    if isinstance(head, list):
        head = head[0] if head else ""
    if isinstance(tail, list):
        tail = tail[0] if tail else ""

    head_norm = normalize_text(head)
    tail_norm = normalize_text(tail)

    src = node_id_map.get(head_norm)
    tgt = node_id_map.get(tail_norm)

    if src and tgt and src != tgt:
        graph.add_edge(src, tgt,
                       relation=rel.get("relation", "related_to"),
                       score=rel.get("score", 1.0))


# ── Task 4: Co-occurrence value anchoring ─────────────────────────────────────

# Labels that represent numeric/temporal leaf nodes
_VALUE_LABELS = {"Quantitative Value", "Unit of Measure"}
# Labels that are meaningful subject nodes
_SUBJECT_LABELS = {
    "ESG Metric", "Sustainability Framework", "Company",
    "Person", "Partnership", "Internal Tool", "Internal Program",
}


def _link_cooccurring_values(graph: nx.DiGraph) -> None:
    """
    Add MEASURES edges from subject entity nodes to Quantitative Value nodes
    that share the same page_number and have no existing in-edges.

    This converts isolated numeric islands into connected metric observations
    without requiring LLM inference.
    """
    # Collect value nodes that are still isolated (no in-edges)
    value_nodes = [
        (nid, d) for nid, d in graph.nodes(data=True)
        if d.get("label") in _VALUE_LABELS
        and d.get("page_number") is not None
        and graph.in_degree(nid) == 0
    ]

    # Collect subject nodes indexed by page
    page_subjects: dict[int, list[tuple]] = {}
    for nid, d in graph.nodes(data=True):
        if d.get("label") in _SUBJECT_LABELS and d.get("page_number") is not None:
            pg = int(d["page_number"])
            page_subjects.setdefault(pg, []).append((nid, d))

    edges_added = 0
    for vid, vdata in value_nodes:
        pg = int(vdata["page_number"])
        subjects_on_page = page_subjects.get(pg, [])
        if not subjects_on_page:
            continue

        # Pick the highest-scored subject on the same page as the anchor
        best_subject = max(subjects_on_page, key=lambda x: x[1].get("score", 0))
        graph.add_edge(best_subject[0], vid, relation="MEASURES")
        edges_added += 1

    logging.info("Co-occurrence linker: added %d MEASURES edges", edges_added)
