import logging


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

    enriched = 0
    for node_id, data in graph.nodes(data=True):
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

        # Find page number from offset
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

    logging.info("Metadata enrichment: %d / %d nodes got page_number + context",
                 enriched, graph.number_of_nodes())
    return graph
