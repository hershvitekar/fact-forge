import logging
import re
import networkx as nx
import json
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from difflib import SequenceMatcher
from .normalization import normalize_text, should_filter_entity, reclassify_entity_label

def slugify(text):
    if not text:
        return "unknown"
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

# ── Navigational Noise Pruning (Task 12) ──────────────────────────────
NAVIGATIONAL_KEYWORDS = [
    r"\bletter\b", r"\bleadership\b", r"\bprogress\b", r"\bplan\b", r"\bapproach\b",
    r"\bculture\b", r"\bsafety\b", r"\bquality\b", r"\bmessage\b", r"\boverview\b",
    r"\bhighlights\b", r"\bforward\b", r"\bcontents\b", r"\bappendix\b", r"\bglossary\b",
    r"\bmethodology\b", r"\bintroduction\b", r"\bcontext\b", r"\bframework\b",
    r"\babout\b", r"\breport\b", r"\bstrategy\b", r"\bvision\b", r"\bmission\b"
]

def prune_navigational_noise(graph):
    """
    Remove nodes that represent document sections/navigation rather than actual ESG facts.
    Logic:
    1. Node is NOT a core ESG fact type (Metric, Observation, Target, Event, Unit).
    2. Node text matches navigational regexes.
    3. Node degree is low (<= 2).
    4. Node is NOT connected to an ESG Metric.
    """
    logging.info("Pruning navigational noise...")
    nodes_to_remove = []
    
    # Core types we never prune this way
    protected_types = {"ESG Metric", "MetricObservation", "Target", "Event", "Quantitative Value", "Unit of Measure"}
    
    nav_pattern = re.compile("|".join(NAVIGATIONAL_KEYWORDS), re.IGNORECASE)
    
    for n, d in list(graph.nodes(data=True)):
        label = d.get("label", "")
        if label in protected_types:
            continue
            
        text = d.get("text", "") or d.get("original_text", "")
        if not text:
            continue
            
        # Check if it looks like navigation
        if nav_pattern.search(text):
            # Check connectivity to metrics
            is_linked_to_metric = False
            for neighbor in graph.neighbors(n):
                if graph.nodes[neighbor].get("label") == "ESG Metric":
                    is_linked_to_metric = True
                    break
            if not is_linked_to_metric:
                for pred in graph.predecessors(n):
                    if graph.nodes[pred].get("label") == "ESG Metric":
                        is_linked_to_metric = True
                        break
            
            # If not linked to a metric and low degree, it's likely noise
            # (degree <= 2 usually means it's only connected to a page and a pillar/company)
            if not is_linked_to_metric and graph.degree(n) <= 2:
                nodes_to_remove.append(n)
                
    if nodes_to_remove:
        graph.remove_nodes_from(nodes_to_remove)
        logging.info("Pruned %d navigational noise nodes", len(nodes_to_remove))
    return graph



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

        node_id = f"{slugify(label)}_{slugify(norm_text)}"
        node_id_map[norm_text] = node_id

        attrs = dict(
            text=norm_text,
            original_text=text,
            label=label,
            score=entity["score"],
            type="entity",
            centrality=entity.get("centrality", 0.0) or 0.0,
        )
        # Preserve page/context if present (ensure no None values)
        if entity.get("page_number") is not None:
            attrs["page_number"] = entity["page_number"]
        
        attrs["context"] = entity.get("context") or ""

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

    # 3. Add internal metadata/offsets to nodes for proximity linking
    for entity in entities:
        norm_text = normalize_text(entity["text"], label=entity["label"])
        node_id = node_id_map.get(norm_text)
        if node_id and graph.has_node(node_id):
            graph.nodes[node_id]["start_offset"] = entity.get("start", 0)

    # ── Cross-entity relationship linking (Tier 1 & 2) ────────────────────────
    _add_cross_entity_relationships(graph, main_company_node)

    logging.info("Graph built: %d nodes, %d edges",
                 graph.number_of_nodes(), graph.number_of_edges())
    return graph


def link_after_enrichment(graph: nx.DiGraph, table_facts: list = None, regulatory_map: dict = None, models = None) -> None:
    """
    Public entry point: add MEASURES edges and process structured table data.
    Now supports regulatory_map for ESGBert-driven anchoring.
    """
    # Pre-create standard nodes from the global question bank
    _create_standard_nodes(graph, regulatory_map)
    
    if table_facts:
        _process_table_facts(graph, table_facts, regulatory_map)
    
    _link_cooccurring_values(graph)
    
    # Final semantic pass using embeddings if available
    if models and models.embedder:
        _semantic_mapping_pass(graph, models)

def _create_standard_nodes(graph, regulatory_map):
    """
    Pre-creates nodes for each regulatory indicator in the global bank.
    Ensures that standard nodes exist even if not discovered in the current document.
    """
    bank_path = Path("eval_engine/global_question_bank.json")
    if not bank_path.exists():
        logging.warning("Global question bank missing - skipping standard node creation")
        return
    
    with open(bank_path, 'r', encoding='utf-8') as f:
        bank_data = json.load(f)
        questions = bank_data.get("questions", [])

    for q_data in questions:
        q_id = q_data["id"]
        # Standard ID format used by the evaluator
        std_node_id = f"std_metric_{slugify(q_id)}"
        
        if not graph.has_node(std_node_id):
            graph.add_node(std_node_id, 
                           text=q_data["standard_question"], 
                           label="Standard ESG Metric",
                           topic=q_data.get("topic"),
                           category=q_data.get("category"),
                           id_code=q_id,
                           type="standard")
            logging.debug("Created standard node: %s", std_node_id)

def _process_table_facts(graph, facts, regulatory_map=None):
    """
    Directly inject facts extracted from tables into the graph.
    Improved Logic: Uses 'Header-Aware Anchoring' to prevent collisions on the same page.
    """
    logging.info("Graph Builder: Injecting %d facts from tables", len(facts))
    for f in facts:
        metric_name = f["metric"]
        page = f.get("page", 0)
        table_heading = f.get("heading", "")
        
        obs = {
            "metric": metric_name,
            "value": f["value"],
            "year": f["year"],
            "unit": f.get("unit", ""),
            "context": f.get("context", "")
        }
        
        # Find if we have a company node to anchor to
        company_node = None
        for nid, ndata in graph.nodes(data=True):
            if ndata.get("label") == "Company":
                company_node = nid
                break
        
        # Create a context-aware name to prevent collisions (Task 12)
        contextual_name = f"{table_heading} {metric_name}" if table_heading else metric_name
        
        # Use the contextual name for structured handling
        _handle_observation(graph, obs, company_node, contextual_name=contextual_name)
        
        # Determine the metric_id (must match what _handle_observation generated)
        metric_id = f"esg_metric_{slugify(normalize_text(contextual_name, label='ESG Metric'))}"
        
        if not graph.has_node(metric_id):
            graph.add_node(metric_id, text=metric_name, label="ESG Metric", type="metric")
            # Assign Pillar (Topic) immediately to assist anchoring
            text_for_pillar = (metric_name + " " + table_heading).lower()
            for pillar, keywords in _ESG_PILLAR_KEYWORDS.items():
                if any(kw in text_for_pillar for kw in keywords):
                    graph.nodes[metric_id]["topic"] = pillar
                    break
            
        if company_node:
            graph.add_edge(company_node, metric_id, relation="REPORTS_METRIC")

        # Add heading context and page info to the metric node
        graph.nodes[metric_id]["table_heading"] = table_heading
        graph.nodes[metric_id]["page_number"] = page

        # ── Precision Anchoring ──────────────────────────────────────────────
        if regulatory_map:
            # 1. First, check how many standards are active on this specific page
            page_standards = []
            for q_id, anchors in regulatory_map.items():
                if any(a["page"] == page for a in anchors):
                    page_standards.append(q_id)
            
            # 2. Heuristic: If only ONE standard is on this page, link it directly (Safe Fallback)
            # HARDENED: Only link if the pillar matches (prevents SOC_GENDER_PAY hijacking)
            if len(page_standards) == 1:
                q_id = page_standards[0]
                std_node_id = f"std_metric_{slugify(q_id)}"
                if graph.has_node(std_node_id):
                    # Get pillars for both
                    std_pillar = graph.nodes[std_node_id].get("topic", "").lower()
                    metric_pillar = graph.nodes[metric_id].get("topic", "").lower()
                    
                    if std_pillar == metric_pillar or not metric_pillar:
                        graph.add_edge(metric_id, std_node_id, 
                                       relation="MAPPED_TO", 
                                       confidence=0.85, 
                                       method="single_anchor_fallback")
                    else:
                        logging.warning("PILLAR MISMATCH: Refusing to anchor '%s' (%s) to '%s' (%s)", 
                                        metric_name, metric_pillar, q_id, std_pillar)
            
            # 3. Precision: If multiple standards, use Header + Keyword Matching
            elif len(page_standards) > 1:
                # Load keywords for disambiguation
                bank_path = Path("eval_engine/global_question_bank.json")
                questions = {}
                if bank_path.exists():
                    with open(bank_path, 'r', encoding='utf-8') as f:
                        bank = json.load(f)
                        questions = {q["id"]: q for q in bank.get("questions", [])}
                
                for q_id in page_standards:
                    std_node_id = f"std_metric_{slugify(q_id)}"
                    if not graph.has_node(std_node_id):
                        continue
                    
                    q_data = questions.get(q_id, {})
                    keywords = q_data.get("keywords", [])
                    
                    # Check the anchors for this specific standard on this page
                    anchors = regulatory_map[q_id]
                    for anchor in anchors:
                        if anchor["page"] == page:
                            ctx = anchor["context"].lower()
                            heading_low = table_heading.lower()
                            metric_low = metric_name.lower()
                            
                            # A. Structural Match (Header context)
                            header_match = (ctx in heading_low) or (heading_low in ctx)
                            
                            # B. Semantic Match (Metric Name vs Standard Keywords)
                            # HARDENED: Only use keywords with >= 5 chars for substring matching
                            keyword_match = any(kw.lower() == metric_low or (len(kw) >= 5 and kw.lower() in metric_low) for kw in keywords)
                            
                            # To link, we need a Header Match AND a Keyword Match 
                            # OR a very strong Keyword Match if the header is generic (like "Principle 6")
                            if (header_match and keyword_match) or (keyword_match and len(keywords) > 0):
                                graph.add_edge(metric_id, std_node_id, 
                                               relation="MAPPED_TO", 
                                               confidence=0.98, 
                                               method="precision_keyword_anchor")
                                break
            
            # 4. Global Fallback: Keyword matching even if the page doesn't match
            # This catches metrics in summary tables or appendixes
            if not any(d.get("relation") == "MAPPED_TO" for _, _, d in graph.out_edges(metric_id, data=True)):
                # Load keywords if not already loaded
                bank_path = Path("eval_engine/global_question_bank.json")
                if bank_path.exists():
                    with open(bank_path, 'r', encoding='utf-8') as f:
                        bank = json.load(f)
                        for q in bank.get("questions", []):
                            keywords = q.get("keywords", [])
                            metric_low = metric_name.lower()
                            if any(kw.lower() == metric_low or (len(kw) >= 5 and kw.lower() in metric_low) for kw in keywords):
                                std_node_id = f"std_metric_{slugify(q['id'])}"
                                if graph.has_node(std_node_id):
                                    graph.add_edge(metric_id, std_node_id, 
                                                   relation="MAPPED_TO", 
                                                   confidence=0.75, 
                                                   method="global_keyword_fallback")
                                    break

def _semantic_mapping_pass(graph, models):
    """Final embedding pass to catch anything the structural discovery missed."""
    # This can be expanded later for deep semantic linking
    pass


# ── Structured fact handlers ───────────────────────────────────────────────────

def _handle_observation(graph, obs, company_node, contextual_name=None):
    """
    Create structured nodes and edges for a MetricObservation.
    Structure: Metric -MEASURES-> Quantitative Value -reported_at-> Reporting Year
    """
    display_name = obs.get("metric", "Unknown Metric")
    # POLISH: Strip footnotes (asterisks) from metric names and search keys
    display_name = display_name.replace("*", "").strip()
    
    # Use contextual_name if provided to ensure ID stability
    search_name = contextual_name if contextual_name else display_name
    search_name = search_name.replace("*", "").strip()
    
    metric_name = normalize_text(search_name, label="ESG Metric")
    
    # POLISH: Strip footnotes from raw values before storage
    raw_val = str(obs.get("value", ""))
    clean_raw_val = raw_val.replace("*", "").strip()
    unit_name   = normalize_text(obs.get("unit", ""), label="Unit of Measure")
    year        = str(obs.get("year", "")).strip()
    if year.lower() == "none": year = ""

    metric_id = f"esg_metric_{slugify(metric_name)}"
    if not graph.has_node(metric_id):
        graph.add_node(metric_id, text=metric_name, label="ESG Metric", type="metric", context=obs.get("context", ""))

    if company_node:
        graph.add_edge(company_node, metric_id, relation="REPORTS_METRIC")

    # Create a unique ID for this specific observation value
    val_id = f"val_{slugify(metric_name)}_{slugify(raw_val)}_{slugify(year)}"
    
    val_attrs = {
        "text": raw_val,
        "label": "Quantitative Value",
        "type": "value",
        "raw_value": raw_val,
        "context": obs.get("context", "")
    }
    try:
        val_attrs["value_float"] = float(raw_val)
    except:
        pass

    graph.add_node(val_id, **val_attrs)
    
    # Link Metric to Value
    graph.add_edge(metric_id, val_id, relation="MEASURES")

    # Link Value to Unit
    if unit_name:
        unit_id = f"unit_{slugify(unit_name)}"
        if not graph.has_node(unit_id):
            graph.add_node(unit_id, text=unit_name, label="Unit of Measure", type="unit")
        graph.add_edge(val_id, unit_id, relation="has_unit")

    # Link Value to Year
    if year:
        year_id = f"reporting_year_{slugify(year)}"
        if not graph.has_node(year_id):
            graph.add_node(year_id, text=year, label="Reporting Year", type="time")
        graph.add_edge(val_id, year_id, relation="reported_at")


def _handle_target(graph, target, company_node):
    """Create structured nodes and edges for a Target."""
    target_type = target.get("target_type", "General Target")
    year_raw    = target.get("target_year")
    year        = str(year_raw).strip() if year_raw is not None else ""
    if year.lower() == "none": year = ""
    context     = target.get("context", "")

    target_id = f"target_{slugify(target_type)}_{slugify(year)}"
    if not graph.has_node(target_id):
        graph.add_node(target_id,
                       text=f"{target_type} ({year})",
                       label="Target",
                       target_type=target_type, year=year,
                       context=context,
                       type="target")

    if company_node:
        graph.add_edge(company_node, target_id, relation="HAS_TARGET", context=context)


def _handle_event(graph, event, company_node):
    """Create a rich edge for an Event, linking Company directly to Metric."""
    if not company_node:
        return
        
    event_type = event.get("event_type", "OBSERVATION").upper().replace(" ", "_")
    metric_name = normalize_text(event.get("metric", "Unknown Metric"), label="ESG Metric")
    
    raw_val    = str(event.get("value", ""))
    try:
        val_float = float(raw_val)
    except ValueError:
        val_float = None
        
    unit       = event.get("unit", "")
    year_raw   = event.get("year")
    year       = str(year_raw).strip() if year_raw is not None else ""
    if year.lower() == "none": year = ""
    context    = event.get("context", "")

    metric_id = f"esg_metric_{slugify(metric_name)}"
    if not graph.has_node(metric_id):
        graph.add_node(metric_id, text=metric_name, label="ESG Metric", type="metric")

    edge_attrs = {
        "relation": event_type,
        "raw_value": raw_val,
        "unit": unit,
        "year": year,
        "context": context or ""
    }
    if val_float is not None:
        edge_attrs["value_float"] = val_float

    graph.add_edge(company_node, metric_id, **edge_attrs)


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
    that share the same page_number, prioritizing the NEAREST subject in text.
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

        v_offset = vdata.get("start_offset", 0)
        
        # Proximity Anchoring: Find the subject with the smallest character distance
        # to the value node, provided it's within a reasonable window or on the same page.
        def calc_dist(s_tuple):
            s_offset = s_tuple[1].get("start_offset", 0)
            return abs(v_offset - s_offset)

        best_subject = min(subjects_on_page, key=calc_dist)
        
        # Validate: If distance is massive (e.g. > 2000 chars), maybe don't link?
        # For now, we trust the page-level proximity if no better match exists.
        graph.add_edge(best_subject[0], vid, relation="MEASURES")
        edges_added += 1

    logging.info("Co-occurrence linker: added %d proximity-aware MEASURES edges", edges_added)


# ── Cross-entity relationship linking ──────────────────────────────────────────

_FRAMEWORK_ABBREVS = {
    re.compile(r'\bgri\b', re.IGNORECASE): "GRI",
    re.compile(r'\bsasb\b', re.IGNORECASE): "SASB",
    re.compile(r'\btcfd\b', re.IGNORECASE): "TCFD",
    re.compile(r'\biso\s*\d+', re.IGNORECASE): "ISO",
    re.compile(r'\bsdgs?\b', re.IGNORECASE): "SDG",
    re.compile(r'\besrs\b', re.IGNORECASE): "ESRS",
}

_ESG_PILLAR_KEYWORDS = {
    "Environmental": {"climate", "carbon", "emissions", "energy", "water", "waste",
                      "biodiversity", "environmental", "ghg", "scope", "renewable",
                      "electricity", "fuel", "natural gas", "pollution", "tco2e"},
    "Social": {"human rights", "diversity", "inclusion", "employees", "safety",
               "community", "labor", "social", "workforce", "women", "hiring",
               "parental", "disability", "donation", "well-being", "health",
               "proficiency", "turnover", "compensation", "culture"},
    "Governance": {"board", "ethics", "corruption", "transparency", "governance",
                   "audit", "compliance", "risk management", "code of conduct",
                   "whistleblower", "oversight", "integrity"},
}


def _add_cross_entity_relationships(graph, main_company_node):
    """Add Tier 1 & 2 cross-entity relationships after all nodes are built."""
    _link_events_to_metrics(graph)
    _link_targets_to_metrics(graph)
    _link_metrics_to_frameworks(graph)
    _link_company_hierarchy(graph, main_company_node)
    _link_temporal_observations(graph)
    _add_esg_pillar_nodes(graph)


def _fuzzy_score(a, b):
    """Combined substring + token-overlap + sequence similarity."""
    al, bl = a.lower().strip(), b.lower().strip()
    if not al or not bl:
        return 0.0
    if al in bl or bl in al:
        return 0.9
    sa, sb = set(al.split()), set(bl.split())
    jaccard = len(sa & sb) / len(sa | sb) if (sa and sb) else 0.0
    seq = SequenceMatcher(None, al, bl).ratio()
    return max(jaccard, seq)


def _link_events_to_metrics(graph):
    """Link Event nodes to their related ESG Metric nodes via EVENT_ABOUT."""
    event_nodes = [(n, d) for n, d in graph.nodes(data=True) if d.get("type") == "event"]
    metric_nodes = [(n, d) for n, d in graph.nodes(data=True)
                    if d.get("type") == "metric" or d.get("label") == "ESG Metric"]
    if not metric_nodes:
        return

    edges_added = 0
    for eid, edata in event_nodes:
        event_metric = edata.get("metric", "")
        if not event_metric or event_metric.lower() in ("metric", "unknown", ""):
            continue
        best_match, best_score = None, 0.0
        for mid, mdata in metric_nodes:
            score = _fuzzy_score(event_metric, mdata.get("text", ""))
            if score > best_score:
                best_score, best_match = score, mid
        if best_match and best_score >= 0.35 and not graph.has_edge(eid, best_match):
            graph.add_edge(eid, best_match, relation="EVENT_ABOUT", score=best_score)
            edges_added += 1

    logging.info("Cross-linker: added %d EVENT_ABOUT edges", edges_added)


def _link_targets_to_metrics(graph):
    """Link Target nodes to the ESG Metrics they reference via TARGET_FOR."""
    target_nodes = [(n, d) for n, d in graph.nodes(data=True) if d.get("type") == "target"]
    metric_nodes = [(n, d) for n, d in graph.nodes(data=True)
                    if d.get("type") == "metric" or d.get("label") == "ESG Metric"]
    if not metric_nodes:
        return

    edges_added = 0
    for tid, tdata in target_nodes:
        target_text = tdata.get("target_type", "") or tdata.get("text", "")
        if not target_text:
            continue
        best_match, best_score = None, 0.0
        for mid, mdata in metric_nodes:
            score = _fuzzy_score(target_text, mdata.get("text", ""))
            if score > best_score:
                best_score, best_match = score, mid
        if best_match and best_score >= 0.3 and not graph.has_edge(tid, best_match):
            graph.add_edge(tid, best_match, relation="TARGET_FOR", score=best_score)
            edges_added += 1

    logging.info("Cross-linker: added %d TARGET_FOR edges", edges_added)


def _link_metrics_to_frameworks(graph):
    """Link ESG Metrics to Sustainability Frameworks via GOVERNED_BY."""
    # Index framework nodes by abbreviation
    fw_by_abbrev = {}
    for n, d in graph.nodes(data=True):
        if d.get("label") == "Sustainability Framework":
            text = d.get("text", "")
            for pattern, abbrev in _FRAMEWORK_ABBREVS.items():
                if pattern.search(text):
                    fw_by_abbrev[abbrev] = n

    metric_nodes = [(n, d) for n, d in graph.nodes(data=True)
                    if d.get("type") == "metric" or d.get("label") == "ESG Metric"]

    edges_added = 0
    for mid, mdata in metric_nodes:
        text = (mdata.get("text", "") + " " + (mdata.get("original_text", "") or "")).strip()
        for pattern, abbrev in _FRAMEWORK_ABBREVS.items():
            if pattern.search(text):
                fw_node = fw_by_abbrev.get(abbrev)
                if fw_node and fw_node != mid and not graph.has_edge(mid, fw_node):
                    graph.add_edge(mid, fw_node, relation="GOVERNED_BY")
                    edges_added += 1

    logging.info("Cross-linker: added %d GOVERNED_BY edges", edges_added)


def _link_company_hierarchy(graph, main_company_node):
    """
    Link subsidiary/partner Company nodes to the main company.
    Strict Rule: Only link if corporate keywords are present in context
    or if it's a known subsidiary.
    """
    if not main_company_node:
        return
    
    # Keywords that suggest a hierarchy relationship
    HIERARCHY_KEYWORDS = {"subsidiary", "partner", "division", "segment", "joint venture", "group", "acquired"}
    # Substances/contexts to explicitly avoid linking as subsidiaries
    NON_COMPANY_CONTEXTS = {"metric context", "substance", "fuel", "gas", "oil", "emissions"}

    company_nodes = [(n, d) for n, d in graph.nodes(data=True)
                     if d.get("label") == "Company" and n != main_company_node]
    
    edges_added = 0
    for cid, cdata in company_nodes:
        text = (cdata.get("text", "") or "").lower()
        context = (cdata.get("context", "") or "").lower()
        
        # Don't link if it's been reclassified or matches a "substance" type
        if cdata.get("label") in NON_COMPANY_CONTEXTS:
            continue
            
        # Only link if the context explicitly mentions a corporate relationship
        # OR if it's a very clear company name (proper noun title case check)
        is_explicit = any(kw in context for kw in HIERARCHY_KEYWORDS)
        
        if is_explicit and not graph.has_edge(cid, main_company_node):
            graph.add_edge(cid, main_company_node, relation="SUBSIDIARY_OF")
            edges_added += 1
            
    logging.info("Cross-linker: added %d validated SUBSIDIARY_OF edges", edges_added)


def _link_temporal_observations(graph):
    """Link observations of the same metric across years via YEAR_OVER_YEAR."""
    metric_obs = {}  # metric_node_id -> [(obs_id, year)]
    for src, tgt, edata in graph.edges(data=True):
        if edata.get("relation") == "HAS_OBSERVATION":
            year = graph.nodes.get(tgt, {}).get("year", "")
            if year and year != "None":
                metric_obs.setdefault(src, []).append((tgt, year))

    edges_added = 0
    for _, obs_list in metric_obs.items():
        if len(obs_list) < 2:
            continue
        obs_list.sort(key=lambda x: x[1])
        for i in range(len(obs_list) - 1):
            earlier, later = obs_list[i][0], obs_list[i + 1][0]
            if not graph.has_edge(earlier, later):
                graph.add_edge(earlier, later, relation="YEAR_OVER_YEAR")
                edges_added += 1
    logging.info("Cross-linker: added %d YEAR_OVER_YEAR edges", edges_added)


def _add_esg_pillar_nodes(graph):
    """Create Environmental/Social/Governance super-nodes and categorize entities."""
    for pillar in ("Environmental", "Social", "Governance"):
        pid = f"pillar_{pillar.lower()}"
        if not graph.has_node(pid):
            graph.add_node(pid, text=pillar, label="ESG Pillar", type="pillar")

    categorizable = {"ESG Metric", "Sustainability Framework", "Event",
                     "Target", "MetricObservation", "Internal Program"}
    edges_added = 0
    for nid, ndata in list(graph.nodes(data=True)):
        if ndata.get("type") == "pillar" or ndata.get("label") not in categorizable:
            continue
        text = (ndata.get("text", "") + " " + (ndata.get("metric", "") or "")
                + " " + (ndata.get("event_type", "") or "")
                + " " + (ndata.get("target_type", "") or "")).lower()
        for pillar, keywords in _ESG_PILLAR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                pid = f"pillar_{pillar.lower()}"
                if not graph.has_edge(nid, pid):
                    graph.add_edge(nid, pid, relation="CATEGORIZED_AS")
                    # Task 12: Also set the topic attribute directly on the node for fast lookup
                    graph.nodes[nid]["topic"] = pillar
                    edges_added += 1
    logging.info("Cross-linker: added %d CATEGORIZED_AS edges (ESG pillars)", edges_added)
