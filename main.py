import logging
import argparse
import sys
import torch
import json
from collections import Counter
# Workaround for Python 3.13 / Torch JIT compatibility issues with DeBERTa models
torch.jit._state.disable()

from pathlib import Path

from model_loader import load_models
from parsers.pdf_parser import parse_document
from discovery.spacy_prescan import run_spacy_prescan
from discovery.taxonomy import discover_taxonomy
from classification.esg_topics import classify_esg_topics
from classification.quant_qual import extract_quant_qual
from extraction.entity_extract import extract_entities
from extraction.section_ranker import rank_sections  # used by taxonomy discovery
from assembly.graph_builder import link_after_enrichment
from extraction.relation_extract import extract_relations
from extraction.llm_relations import resolve_ambiguities
from extraction.event_extractor import extract_events
from assembly.dedup import deduplicate_entities
from assembly.graph_builder import build_graph
from assembly.exporter import export_kg
from enrichment.metadata import enrich_metadata
from enrichment.algorithms import run_graph_algorithms
from insight.narrative import generate_narrative
import networkx as nx


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def write_insights(text: str, destination: Path) -> None:
    with destination.open("w", encoding="utf-8") as handle:
        handle.write(text)


def main(source_path: str = None, skip_llm: bool = False, relation_threshold: float = 0.08, 
         llm_only: bool = False, save_intermediates: bool = True) -> None:
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    source_path = source_path or "input/document.pdf"
    print("\n" + "="*60)
    print(f"🚀 ESG KNOWLEDGE GRAPH PIPELINE v2.1")
    print(f"📄 Source: {source_path}")
    print("="*60 + "\n")
    
    logging.info("[STAGE 1/5] PARSING & DISCOVERY")
    
    document = parse_document(source_path)
    
    report_name = Path(source_path).stem
    report_out_dir = OUTPUT_DIR / report_name
    report_out_dir.mkdir(parents=True, exist_ok=True)
    
    cache_path = report_out_dir / "intermediates.json"

    if llm_only:
        if not cache_path.exists():
            logging.error("Intermediates cache not found at %s. Run a full pipeline with --save-intermediates first.", cache_path)
            return
        logging.info("Loading intermediate data from cache...")
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
            sentences = cache.get("sentences", [])
            taxonomy = cache.get("taxonomy", {})
            topics = cache.get("topics", {})
            quant_qual = cache.get("quant_qual", {})
            entities = cache.get("entities", [])
            relations = cache.get("relations", [])
        document["sentences"] = sentences  # attach for downstream modules
    else:
        logging.info("Loading NLP models into RAM...")
        models = load_models()
        logging.info("Running document prescan...")
        prescan = run_spacy_prescan(document, models.nlp)
        sentences = prescan.get("sentences", [])
        document["sentences"] = sentences  # attach for downstream modules
        
        taxonomy = discover_taxonomy(document, prescan)
        logging.info("Classifying ESG thematic coverage...")
        topics = classify_esg_topics(document, models)
        quant_qual = extract_quant_qual(document)
        logging.info("[STAGE 2/5] EXTRACTION")
        entities = extract_entities(document, models.gliner, sentences)
        relations = extract_relations(document, models.glirel, sentences, entities)

        if save_intermediates:
            logging.info("Saving intermediate data to %s", cache_path)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({
                    "sentences": sentences,
                    "taxonomy": taxonomy,
                    "topics": topics,
                    "quant_qual": quant_qual,
                    "entities": entities,
                    "relations": relations
                }, f, indent=2)

    # 1. Identify main company (Heuristic) - Move up for LLM context
    company_counts = Counter([e["text"] for e in entities if e["label"] == "Company" and len(e["text"]) > 3])
    noise = {"nlp", "company", "group", "entity", "report"}
    top_companies = [c for c, count in company_counts.most_common() if c.lower() not in noise]
    main_company = top_companies[0] if top_companies else None
    if main_company:
        logging.info("Global Anchor identified: %s", main_company)

    logging.info("[STAGE 3/5] TARGETED LLM DISAMBIGUATION")
    if skip_llm:
        complex_relations = relations
    else:
        complex_relations = resolve_ambiguities(document, entities, relations, main_company=main_company)

    # 3. Extract rule-based events
    events = extract_events(sentences)
    complex_relations += events

    # 4. Graph Assembly
    deduped_entities = deduplicate_entities(entities)
    graph = build_graph(document, deduped_entities, complex_relations, taxonomy, topics, quant_qual, 
                        relation_threshold=relation_threshold, main_company=main_company)
    
    graph = enrich_metadata(graph, document)

    # Co-occurrence value linker runs AFTER metadata enrichment because
    # page_number attributes are only populated by enrich_metadata().
    link_after_enrichment(graph)

    isolated_nodes = list(nx.isolates(graph))
    if isolated_nodes:
        graph.remove_nodes_from(isolated_nodes)
        logging.info("Pruned %d isolated nodes from the graph to reduce noise", len(isolated_nodes))

    logging.info("[STAGE 4/5] GRAPH ENRICHMENT & ALGORITHMS")
    graph = run_graph_algorithms(graph)

    logging.info("[STAGE 5/5] INSIGHT GENERATION & EXPORT")
    # Both paths use generate_narrative — skip_llm forces the structured fallback
    # inside narrative.py (LLM query is skipped when LLM is unavailable anyway).
    # This ensures entity-level data always appears in insights.md.
    narrative = generate_narrative(graph, topics, quant_qual, document, output_dir=report_out_dir)

    # 5. Export
    graph_path = report_out_dir / "graph.graphml"
    insights_path = report_out_dir / "insights.md"
    logging.info("Exporting graph to %s", graph_path)
    nx.write_graphml(graph, str(graph_path))

    logging.info("Exporting insights to %s", insights_path)
    write_insights(narrative, insights_path)

    # V2: Export structured data
    export_kg(graph, report_out_dir)
    logging.info("Pipeline finished successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ESG disclosure NLP pipeline.")
    parser.add_argument("source_path", nargs="?", default="input/document.pdf", help="Path to the PDF document.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM-based relation extraction and narrative generation.")
    parser.add_argument("--llm-only", action="store_true", help="Skip extraction and only run LLM steps using cached intermediates.")
    parser.add_argument("--no-cache", action="store_false", dest="save_intermediates", help="Do not save intermediate extraction results to cache.")
    parser.set_defaults(save_intermediates=True)
    parser.add_argument("--relation-threshold", type=float, default=0.08, help="Minimum confidence score for relationships (0.0 to 1.0).")
    
    args = parser.parse_args()
    main(source_path=args.source_path, 
         skip_llm=args.skip_llm, 
         relation_threshold=args.relation_threshold,
         llm_only=args.llm_only,
         save_intermediates=args.save_intermediates)