import logging
import re
import config


def enrich_metadata(graph, document):
    """Enrich the graph with document metadata and extracted attributes.
    
    Searches for each entity's original_text (pre-normalization) in the document
    to locate its page number and surrounding context snippet. Falls back to the
    normalized text if original_text is not available.
    """
    logging.info("Enriching metadata")
    graph.graph["document_title"] = document.get("source_path")
    graph.graph["page_count"] = len(document.get("pages", []))

    text = document.get("text", "")
    pages = document.get("pages", [])

    # Ensure Unknown Unit node exists
    if "unknown_unit" not in graph:
        graph.add_node("unknown_unit", 
                       label="Unknown Unit", 
                       type="unit", 
                       context="(could not find unit)")

    enriched = 0
    orphans_anchored = 0

    for node_id, data in list(graph.nodes(data=True)):
        if data.get("type") not in ("entity", "observation", "event", "target"):
            continue

        # Prefer original_text for search — it hasn't been title-cased or
        # synonym-mapped, so it's far more likely to appear verbatim in the PDF.
        search_text = data.get("original_text") or data.get("text", "")
        if not search_text:
            continue

        # Try case-sensitive first (fastest), then case-insensitive fallback
        idx = text.find(search_text)
        if idx == -1:
            idx = text.lower().find(search_text.lower())

        if idx == -1:
            continue

        # ── 1. Basic Metadata (Page & Context) ────────────────────────────────
        page_num = 1
        for page in pages:
            if page["start_offset"] <= idx <= page["end_offset"]:
                page_num = page["page_number"]
                break

        graph.nodes[node_id]["page_number"] = page_num

        # Context snippet (100 chars each side for richer context)
        start = max(0, idx - 50)
        end = min(len(text), idx + len(search_text) + 50)
        snippet = text[start:end].replace("\n", " ").strip()
        graph.nodes[node_id]["context"] = f"...{snippet}..."
        enriched += 1

        # ── 2. Orphaned Quantitative Value Anchoring (Task 10) ────────────────
        if data.get("label") == "Quantitative Value":
            # Check if already anchored to a unit or metric
            has_unit = False
            for _, _, edata in graph.edges(node_id, data=True):
                if edata.get("relation") in ("has_unit", "measured_as"):
                    has_unit = True
                    break
            if not has_unit:
                for _, _, edata in graph.in_edges(node_id, data=True):
                    if edata.get("relation") == "measured_as":
                        has_unit = True
                        break
            
            if not has_unit:
                # Search for unit in radius
                start_win = max(0, idx - 100)
                end_win = min(len(text), idx + len(search_text) + 100)
                window_text = text[start_win:end_win]

                unit_found = False
                for pattern_str in config.QUANT_UNITS:
                    match = re.search(pattern_str, window_text, re.IGNORECASE)
                    if match:
                        unit_text = match.group(0).strip()
                        unit_node_id = f"unit_{unit_text.lower()}"
                        if unit_node_id not in graph:
                            graph.add_node(unit_node_id, 
                                           label="Unit of Measure", 
                                           text=unit_text,
                                           type="unit",
                                           context=f"Detected near {search_text}")
                        graph.add_edge(node_id, unit_node_id, relation="has_unit")
                        unit_found = True
                        break
                
                if not unit_found:
                    graph.add_edge(node_id, "unknown_unit", relation="has_unit")
                
                orphans_anchored += 1

    logging.info("Metadata enrichment: %d nodes enriched", enriched)
    if orphans_anchored:
        logging.info("Orphan anchoring: linked %d Quantitative Values to units/unknown", orphans_anchored)

    return graph
