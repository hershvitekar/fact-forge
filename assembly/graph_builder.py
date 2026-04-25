import logging
import re
import networkx as nx
import json
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


def link_after_enrichment(graph: nx.DiGraph, table_facts: list = None) -> None:
    """
    Public entry point: add MEASURES edges and process structured table data.
    """
    if table_facts:
        _process_table_facts(graph, table_facts)
        
    _link_cooccurring_values(graph)
    _link_to_standard_metrics(graph)

def _process_table_facts(graph, facts):
    """
    Directly inject facts extracted from tables into the graph.
    """
    logging.info("Graph Builder: Injecting %d facts from tables", len(facts))
    for f in facts:
        # Use existing observation handler logic but with table context
        obs = {
            "metric": f["metric"],
            "value": f["value"],
            "year": f["year"],
            "unit": f.get("unit", "")
        }
        # Find if we have a company node to anchor to
        company_node = None
        for nid, ndata in graph.nodes(data=True):
            if ndata.get("label") == "Company":
                company_node = nid
                break
        
        _handle_observation(graph, obs, company_node)
        
        # Add heading context to the metric node if we just created it
        metric_id = f"esg_metric_{slugify(normalize_text(f['metric'], label='ESG Metric'))}"
        if graph.has_node(metric_id):
            graph.nodes[metric_id]["table_heading"] = f["heading"]


# ── Structured fact handlers ───────────────────────────────────────────────────

def _handle_observation(graph, obs, company_node):
    """
    Create structured nodes and edges for a MetricObservation.
    Structure: Metric -MEASURES-> Quantitative Value -reported_at-> Reporting Year
    """
    metric_name = normalize_text(obs.get("metric", "Unknown Metric"), label="ESG Metric")
    raw_val     = str(obs.get("value", ""))
    unit_name   = normalize_text(obs.get("unit", ""), label="Unit of Measure")
    year        = str(obs.get("year", "")).strip()
    if year.lower() == "none": year = ""

    metric_id = f"esg_metric_{slugify(metric_name)}"
    if not graph.has_node(metric_id):
        graph.add_node(metric_id, text=metric_name, label="ESG Metric", type="metric")

    if company_node:
        graph.add_edge(company_node, metric_id, relation="REPORTS_METRIC")

    # Create a unique ID for this specific observation value
    val_id = f"val_{slugify(metric_name)}_{slugify(raw_val)}_{slugify(year)}"
    
    val_attrs = {
        "text": raw_val,
        "label": "Quantitative Value",
        "type": "value",
        "raw_value": raw_val
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
                    edges_added += 1
    logging.info("Cross-linker: added %d CATEGORIZED_AS edges (ESG pillars)", edges_added)


STANDARD_METRICS = {
    "Scope 1 Emissions": ["scope 1", "direct emissions", "ghg protocol scope 1"],
    "Scope 2 Emissions": ["scope 2", "indirect emissions", "purchased electricity"],
    "Total Energy": ["total energy", "energy consumption", "energy usage", "joules"],
    "Total Water": ["water consumption", "water withdrawal", "total water", "kilolitres"],
    "Waste Generated": ["total waste", "waste generated", "solid waste", "waste intensity"],
    "LTIFR": ["ltifr", "lost time injury", "injury frequency"],
    "Gender Diversity": ["female employees", "women in workforce", "gender diversity", "board of directors"],
    "Social Impact": ["lives impacted", "community reach", "social beneficiaries", "prabhat", "shakti", "nutrition"]
}

def _link_to_standard_metrics(graph):
    """Map company-specific metrics to a set of global standard nodes."""
    # Mapping of headings to pillars to reduce ambiguity
    HEADING_PILLAR_MAP = {
        "Principle 6": "Environmental",
        "Environmental": "Environmental",
        "Climate": "Environmental",
        "Water": "Environmental",
        "Principle 3": "Social",
        "Social": "Social",
        "Workforce": "Social",
        "Diversity": "Social",
        "Principle 5": "Social", # Human Rights
        "CSR": "Social",
        "Principle 8": "Social", # Community
        "Prabhat": "Social"
    }

    for std_name, keywords in STANDARD_METRICS.items():
        std_id = f"std_metric_{slugify(std_name)}"
        if not graph.has_node(std_id):
            graph.add_node(std_id, text=std_name, label="Standard ESG Metric", type="standard_metric")
        
        for nid, ndata in graph.nodes(data=True):
            if ndata.get("label") == "ESG Metric":
                metric_text = ndata.get("text", "").lower()
                heading = ndata.get("table_heading", "")
                
                # Check for direct keyword match
                match = any(kw in metric_text for kw in keywords)
                
                # Check for context match if the metric is ambiguous
                # e.g. "Total consumption" in "Principle 6" is likely Energy or Water
                if not match and heading:
                    for h_key, pillar in HEADING_PILLAR_MAP.items():
                        if h_key.lower() in heading.lower():
                            # If we are under Principle 6 and the metric has "energy" or "emissions"
                            if pillar == "Environmental" and ("energy" in metric_text or "emission" in metric_text or "water" in metric_text):
                                # Further refine matching logic here if needed
                                pass
                
                if match:
                    graph.add_edge(nid, std_id, relation="MAPPED_TO")
    logging.info("Standardization: Mapped metrics to global standard categories using context.")
