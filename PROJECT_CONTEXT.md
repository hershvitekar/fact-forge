# Fact-Forge — Project Context

> **Purpose of this document:** Drop this file into any LLM conversation to give it full understanding of the fact-forge codebase. It covers architecture, every module, data flow, configuration, and conventions.

---

## 1. What This Project Does

Fact-Forge is a **Python NLP pipeline** that ingests ESG (Environmental, Social, Governance) sustainability reports (PDFs), extracts structured knowledge using a combination of transformer models and an LLM, and builds a typed **Knowledge Graph** (KG). The final outputs are a GraphML file, CSV exports, a quality report, and a professional narrative summary.

**Tech stack:** Python 3.10+, PyTorch, spaCy, GLiNER, GLiREL, ESGBERT (HuggingFace), sentence-transformers, NetworkX, pdfplumber, pyvis. LLM inference via a self-hosted **llama.cpp** server over HTTP.

---

## 2. Directory Structure

```
fact-forge/
├── main.py                  # CLI entry point — orchestrates the 5-stage pipeline
├── config.py                # All constants: model names, thresholds, entity types, relation labels
├── model_loader.py          # Preloads all NLP models into a single Models container
├── graph_viewer.py          # Standalone pyvis visualizer for the output graph
├── requirements.txt         # Python dependencies
├── sample_report.txt        # Tiny sample ESG text for testing
│
├── parsers/
│   └── pdf_parser.py        # PDF → document dict (text + per-page offsets)
│
├── discovery/
│   ├── spacy_prescan.py     # spaCy sentence splitting + NER prescan
│   └── taxonomy.py          # Keyword-based ESG category & section discovery
│
├── classification/
│   ├── esg_topics.py        # ESGBERT-based E/S/G topic scoring
│   └── quant_qual.py        # Regex extraction of quantitative values & qualitative signals
│
├── extraction/
│   ├── entity_extract.py    # GLiNER entity extraction (batched, sentence-level)
│   ├── relation_extract.py  # GLiREL relation extraction (sliding-window paragraphs)
│   ├── llm_relations.py     # LLM-based structured fact extraction (chunked)
│   ├── event_extractor.py   # Rule-based event/target/observation extraction
│   └── section_ranker.py    # Ranks pages by ESG entity density
│
├── assembly/
│   ├── normalization.py     # Text normalization, synonym mapping, entity filtering, label reclassification
│   ├── dedup.py             # Fuzzy entity deduplication (Jaccard + SequenceMatcher)
│   ├── graph_builder.py     # Builds the NetworkX DiGraph with typed nodes & edges
│   └── exporter.py          # Exports to CSV, JSON, GraphML; computes quality grade (A–D)
│
├── enrichment/
│   ├── metadata.py          # Annotates graph nodes with page_number + context snippets
│   └── algorithms.py        # Runs PageRank centrality on the graph
│
├── insight/
│   └── narrative.py         # LLM-generated professional ESG narrative (with structured fallback)
│
├── utils/
│   ├── llm_client.py        # Primary HTTP client for llama.cpp /completion endpoint
│   └── ollama_client.py     # Legacy/alternative llama.cpp client (not used in pipeline)
│
└── output/                  # Generated at runtime (gitignored)
    ├── graph.graphml
    ├── insights.md
    ├── nodes.csv / edges.csv
    ├── observations.csv / observations.json
    ├── graph_quality.json
    └── intermediates.json   # Optional cache for --llm-only mode
```

---

## 3. Pipeline Architecture (5 Stages)

The pipeline runs sequentially through `main.py`:

```
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 1: PARSING & DISCOVERY                                    │
│  pdf_parser → spacy_prescan → taxonomy → esg_topics              │
├──────────────────────────────────────────────────────────────────┤
│  STAGE 2: EXTRACTION                                             │
│  entity_extract (GLiNER) → relation_extract (GLiREL)             │
│  [optional: save intermediates to JSON cache]                    │
├──────────────────────────────────────────────────────────────────┤
│  STAGE 3: LLM COMPLEX REASONING                                 │
│  llm_relations (chunked fact builder) + event_extractor (rules)  │
├──────────────────────────────────────────────────────────────────┤
│  STAGE 4: GRAPH ASSEMBLY & ENRICHMENT                            │
│  dedup → build_graph → enrich_metadata → link_after_enrichment   │
│  → run_graph_algorithms (PageRank)                               │
├──────────────────────────────────────────────────────────────────┤
│  STAGE 5: INSIGHT GENERATION & EXPORT                            │
│  generate_narrative → export GraphML + CSV + quality report      │
└──────────────────────────────────────────────────────────────────┘
```

### Stage-by-stage data flow

| Stage | Input | Output | Key Functions |
|-------|-------|--------|---------------|
| 1 | PDF file path | `document` dict, `sentences[]`, `taxonomy`, `topics` | `parse_document()`, `run_spacy_prescan()`, `discover_taxonomy()`, `classify_esg_topics()` |
| 2 | `document`, `sentences`, models | `entities[]`, `relations[]` | `extract_entities()`, `extract_relations()` |
| 3 | `document`, `relations`, `sentences` | `complex_relations[]` (relations + LLM facts + events) | `infer_complex_relations()`, `extract_events()` |
| 4 | entities, complex_relations, taxonomy, topics | `nx.DiGraph` with typed nodes/edges | `deduplicate_entities()`, `build_graph()`, `enrich_metadata()`, `link_after_enrichment()`, `run_graph_algorithms()` |
| 5 | graph, topics, quant_qual | `insights.md`, CSV/JSON/GraphML files, `graph_quality.json` | `generate_narrative()`, `export_kg()` |

---

## 4. Core Data Structures

### Document dict (output of `parse_document`)
```python
{
    "source_path": str,
    "text": str,           # Full concatenated text
    "pages": [
        {"page_number": int, "text": str, "start_offset": int, "end_offset": int}
    ]
}
```

### Entity dict (output of extraction)
```python
{"text": str, "label": str, "score": float, "start": int, "end": int}
```
Labels come from `config.BASE_ESG_ENTITY_TYPES`: Company, ESG Metric, Unit of Measure, Reporting Year, Quantitative Value, Sustainability Framework.

### Relation dict (GLiREL output)
```python
{"relation": str, "head": str, "tail": str, "score": float}
```

### Structured facts (LLM/event output) — three `type` variants:
```python
# MetricObservation
{"type": "MetricObservation", "company": str, "metric": str, "value": float, "unit": str, "year": int, "confidence": float}
# Target
{"type": "Target", "company": str, "target_type": str, "target_year": int, "baseline_year": int}
# Event
{"type": "Event", "event_type": str, "metric": str, "value": str, "unit": str, "year": str, "context": str}
```

---

## 5. Graph Schema (V2)

The knowledge graph is a **NetworkX DiGraph** with strictly typed nodes and edges.

### Node types (by `type` attribute)

| `type` | `label` examples | Created by |
|--------|-------------------|------------|
| `entity` | Company, ESG Metric, Quantitative Value, Sustainability Framework, Person, Partnership, etc. | `build_graph` from GLiNER entities |
| `observation` | MetricObservation | `_handle_observation` from LLM facts |
| `metric` | ESG Metric | `_handle_observation` (parent of observations) |
| `target` | Target | `_handle_target` from LLM/rule facts |
| `event` | Event | `_handle_event` from LLM/rule facts |
| `time` | Reporting Year | Created alongside observations |

### Edge types (by `relation` attribute)

| Relation | Source → Target |
|----------|-----------------|
| `HAS_OBSERVATION` | metric → observation |
| `REPORTS_METRIC` | company → metric |
| `REPORTED_AT` | observation → year |
| `HAS_TARGET` | company → target |
| `HAS_EVENT` | company → event |
| `MEASURES` | subject entity → quantitative value (co-occurrence linker) |
| GLiREL labels | `measured_as`, `has_unit`, `reported_at`, `belongs_to`, `measures`, `reduces`, `targets`, `partners_with`, `achieves`, `aligns_with` |

### Important ordering constraint
`link_after_enrichment(graph)` **must** be called after `enrich_metadata()` because it relies on `page_number` attributes that metadata enrichment populates.

---

## 6. Module-by-Module Reference

### `config.py`
Central constants file. Key groups:
- **Model identifiers:** `GLINER_MODEL`, `GLIREL_MODEL`, `ESGBERT_MODEL`, `SENTENCE_TRANSFORMER`, `SPACY_MODEL`
- **Thresholds:** `GLINER_CONFIDENCE` (0.5), `GLIREL_CONFIDENCE` (0.08), `SEMANTIC_SIMILARITY_THRESHOLD` (0.75), `FUZZY_MATCH_THRESHOLD` (0.85)
- **Granularity:** `RELATION_PARA_SENTENCES` (4), `ENTITY_BATCH_SIZE` (16)
- **Regex patterns:** `QUANT_UNITS`, `QUANT_COMPARATORS`, `QUANT_TEMPORAL` — used by `quant_qual.py` and `event_extractor.py`
- **`BASE_ESG_ENTITY_TYPES`** — the 6 entity labels for GLiNER
- **`ESG_RELATION_LABELS`** — 10 relation types with natural-language descriptions and type constraints (used as GLiREL soft prompts)
- **LLM endpoint:** `LLM_URL` (default `http://192.168.1.18:8080`)

### `model_loader.py`
- `Models` class: container with attributes `nlp`, `gliner`, `glirel`, `embedder`, `esg_env`, `esg_social`, `esg_gov`
- `load_models()`: loads all 7 models at startup; no model is ever unloaded
- All pipeline functions receive models as parameters (dependency injection)

### `parsers/pdf_parser.py`
- `parse_document(source_path)` → document dict
- Uses `pdfplumber` for PDF; tracks per-page character offsets for later page attribution
- Falls back gracefully on non-PDF files (returns empty text)

### `discovery/spacy_prescan.py`
- `run_spacy_prescan(document, nlp)` → `{"entities": [...], "sentences": [...]}`
- Runs spaCy `en_core_web_trf` page-by-page with `nlp.pipe(batch_size=5)`
- Output `sentences` list is the backbone for all downstream extraction

### `discovery/taxonomy.py`
- `discover_taxonomy(document, prescan)` → `{"categories": [...], "category_counts": {...}, "sections": [...]}`
- Keyword regex matching across 5 ESG categories (environment, social, governance, strategy, targets)

### `classification/esg_topics.py`
- `classify_esg_topics(document, models)` → `{"environment": float, "social": float, "governance": float}`
- Uses ESGBERT text-classification pipelines on a 1000-char sample

### `classification/quant_qual.py`
- `extract_quant_qual(document)` → `{"quantitative": [...], "qualitative": [...]}`
- Regex-based; uses patterns from `config.QUANT_UNITS`, `QUANT_COMPARATORS`, `QUANT_TEMPORAL`

### `extraction/entity_extract.py`
- `extract_entities(document, gliner_model, sentences)` → `entities[]`
- Sentence-level batched extraction via `gliner_model.batch_predict_entities()`
- Adds a heuristic "anchor" company entity from the filename
- Tracks global character offsets for page attribution later

### `extraction/relation_extract.py`
- `extract_relations(document, glirel_model, sentences, entities)` → `relations[]`
- Sliding window (4 sentences, stride 2) over sentences to form paragraphs
- Builds char→token mapping for GLiREL's token-based API
- Filters entities to those within each paragraph's character span

### `extraction/llm_relations.py`
- `infer_complex_relations(document, relations, main_company)` → `relations + structured_facts`
- Chunks full document text (4000 chars, 500 overlap) and prompts the LLM for MetricObservation/Target/Event JSON
- `_parse_llm_response()`: robust JSON extraction with markdown code-block handling and bracket matching

### `extraction/event_extractor.py`
- `extract_events(sentences)` → `events[]` (Event and Target dicts)
- Rule-based: uses `_NUMBER_RE` for numeric pre-extraction, `_ESG_SUBJECT_HINTS` for metric identification
- Detects: reductions, increases, observations, commitments, net-zero targets
- `_best_subject()`: heuristic to find the closest ESG keyword before a numeric value

### `extraction/section_ranker.py`
- `rank_sections(document, entities)` → ranked page list by ESG entity density
- Not directly called in main pipeline (available for future use)

### `assembly/normalization.py`
- `normalize_text(text)` → canonical form (lowercased, synonym-mapped, title-cased)
- `should_filter_entity(text)` → bool: filters stop-entities, pure numbers, PDF artifacts, double-encoded strings, unknown short ALL-CAPS tokens
- `reclassify_entity_label(text, label)` → corrected label: overrides misclassified entities (e.g., internal tools classified as "Company"), detects person names via `[A-Z][a-z]+ [A-Z][a-z]+` regex
- `ESG_SYNONYMS`: maps variant terms to canonical ESG concepts
- `UNIT_MAPPING`: normalizes measurement units
- `PDF_ARTIFACTS`: known garbled strings to filter
- `ENTITY_TYPE_OVERRIDES`: explicit text→label corrections

### `assembly/dedup.py`
- `deduplicate_entities(entities)` → deduplicated list
- Two-pass: exact match dedup → fuzzy dedup within label groups
- `LABEL_GROUPS`: defines which entity labels can be merged (e.g., `env`, `org`, `quant`, `time`)
- Similarity: `max(Jaccard token similarity, SequenceMatcher ratio)` with threshold 0.72
- Skips fuzzy merge for `quant`, `time`, `unit` groups

### `assembly/graph_builder.py`
- `build_graph(...)` → `nx.DiGraph`: main graph constructor
- Processes entities (with filtering + reclassification) then dispatches each relation/fact to type-specific handlers
- `_handle_observation()`, `_handle_target()`, `_handle_event()`: create structured node subgraphs anchored to company
- `_handle_simple_relation()`: adds edges between existing entity nodes (threshold-filtered)
- `link_after_enrichment(graph)` → `_link_cooccurring_values()`: adds MEASURES edges between isolated Quantitative Value nodes and highest-scored subject entities on the same page

### `assembly/exporter.py`
- `export_kg(graph, output_dir)`: writes `observations.json`, `observations.csv`, `nodes.csv`, `edges.csv`
- `export_quality_report(graph, output_dir)`: computes density, isolated node ratio, weakly connected components, node type distribution, and assigns A–D letter grade

### `enrichment/metadata.py`
- `enrich_metadata(graph, document)` → graph with `page_number` and `context` attributes
- Searches for each node's `original_text` (pre-normalization) in the full document text
- Falls back to case-insensitive search if case-sensitive fails

### `enrichment/algorithms.py`
- `run_graph_algorithms(graph)` → graph with `centrality` (PageRank) on each node

### `insight/narrative.py`
- `generate_narrative(graph, topics, quant_qual)` → markdown string
- Builds a rich LLM prompt with entity summaries, observations, targets, events
- Uses `[INST]` / `<<SYS>>` format (Llama-2 chat template)
- `_structured_fallback()`: generates a markdown summary when LLM is unavailable
- `_build_entity_summary()`: extracts high-confidence ESG Metric and Quantitative Value nodes
- `_detect_main_company()`: finds highest-scored Company node

### `utils/llm_client.py`
- `query_llm(prompt, n_predict=512)` → str
- HTTP POST to `{LLM_URL}/completion` (llama.cpp native API)
- Parameters: `temperature=0.0`, `top_p=0.95`, `top_k=40`, `repeat_penalty=1.1`, `cache_prompt=True`
- Returns empty string on any error (graceful degradation)

### `utils/ollama_client.py`
- `query_llama_cpp(prompt)` → str
- Legacy client; hardcoded URL; not used by the pipeline (kept for manual testing)

### `graph_viewer.py`
- `view_graph(file_path)`: standalone script to visualize `graph.graphml`
- Uses pyvis with ForceAtlas2 layout, dark theme, color-coded node types
- Injects a search bar into the HTML output for interactive exploration

---

## 7. CLI Usage

```bash
# Full pipeline
python main.py path/to/report.pdf

# Save intermediates for later LLM-only runs
python main.py path/to/report.pdf --save-intermediates

# Re-run only LLM stages (skip model loading + extraction)
python main.py path/to/report.pdf --llm-only

# Skip all LLM steps (debug extraction only)
python main.py path/to/report.pdf --skip-llm

# Adjust relation confidence threshold
python main.py path/to/report.pdf --relation-threshold 0.05
```

---

## 8. NLP Model Inventory

| Model | Config Key | Library | Purpose |
|-------|-----------|---------|---------|
| `en_core_web_trf` | `SPACY_MODEL` | spaCy | Sentence splitting + NER prescan |
| `urchade/gliner_medium-v2.1` | `GLINER_MODEL` | GLiNER | Typed entity recognition (6 ESG types) |
| `jackboyla/glirel-large-v0` | `GLIREL_MODEL` | GLiREL | Relationship extraction (10 ESG relations) |
| `ESGBERT/EnvironmentalBERT-environmental` | `ESGBERT_MODEL` | HuggingFace transformers | E/S/G topic classification (used 3x) |
| `all-MiniLM-L6-v2` | `SENTENCE_TRANSFORMER` | sentence-transformers | Embedding (loaded but not actively used in pipeline) |
| Self-hosted LLM | `LLM_URL` | llama.cpp | Structured fact extraction + narrative generation |

---

## 9. Key Design Decisions & Conventions

1. **All models loaded once at startup** via `model_loader.py` — never reloaded or unloaded. Every function receives models as parameters.
2. **Intermediate caching** (`--save-intermediates` / `--llm-only`) enables fast iteration on LLM prompts without re-running expensive extraction models.
3. **Graceful LLM degradation:** if the LLM server is unreachable, `query_llm()` returns `""` and `narrative.py` falls back to a structured markdown summary.
4. **Character offset tracking** from PDF parsing through entity extraction enables accurate page attribution in the enrichment stage.
5. **Co-occurrence linking is intentionally deferred** until after metadata enrichment — `link_after_enrichment()` must be called after `enrich_metadata()`.
6. **Entity normalization pipeline:** raw text → `normalize_text()` (synonym + unit mapping) → `should_filter_entity()` (stop-list) → `reclassify_entity_label()` (type correction) → `deduplicate_entities()` (fuzzy merge).
7. **GLiREL relation labels use natural-language descriptions** as soft prompts — richer descriptions increase recall on ESG text patterns.
8. **Torch JIT is disabled** at startup (`torch.jit._state.disable()`) as a workaround for Python 3.13 / DeBERTa compatibility.
9. **Logging:** standard Python logging with `%(asctime)s [%(levelname)s] %(message)s` format. Pipeline stages are clearly numbered in log output.
10. **Output directory** is `output/` relative to the project root, created automatically and gitignored.
