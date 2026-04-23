# Fact Forge — ESG Knowledge Graph Pipeline

A high-fidelity NLP pipeline for extracting Environmental, Social, and Governance (ESG) disclosures from PDF reports and building a structured Knowledge Graph (KG).

## Architecture

The pipeline follows a **code-first, LLM-minimal** philosophy: the knowledge graph is constructed entirely by NLP models and rule-based extractors.  The LLM is used **only** for two narrowly-scoped tasks where NLP alone cannot succeed.

```
PDF Document
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 1 — PARSING & DISCOVERY  (no LLM)       │
│  • PDF → text + pages      (pdfplumber)        │
│  • Sentence splitting      (spaCy)             │
│  • Taxonomy discovery      (TF-IDF + rules)    │
│  • ESG topic classification (ESGBERT)          │
│  • Quantitative/qualitative detection (regex)  │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 2 — EXTRACTION  (no LLM)                │
│  • Entity extraction       (GLiNER)            │
│  • Relation extraction     (GLiREL)            │
│  • Event & target extraction (rule-based)      │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 3 — TARGETED DISAMBIGUATION  (LLM)      │
│  • Orphan value resolution (~15 sentences)     │
│  • Ambiguous metric linking (~10 sentences)    │
│  • Coreference / pronoun anchoring (~15 sents) │
│  → Only ~2K tokens sent to LLM (not full doc)  │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 4 — GRAPH ASSEMBLY & ENRICHMENT (no LLM)│
│  • Entity deduplication    (fuzzy matching)     │
│  • Graph construction      (NetworkX)          │
│  • Co-occurrence linking   (page proximity)    │
│  • Metadata enrichment     (page/context)      │
│  • Graph algorithms        (centrality, etc.)  │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 5 — INSIGHT GENERATION  (LLM)           │
│  • Narrative summary from structured graph     │
│  • Export: GraphML, CSV, Markdown              │
└────────────────────────────────────────────────┘
```

### LLM Usage Summary

| Stage | LLM? | Tokens | Purpose |
|-------|------|--------|---------|
| 1. Parsing & Discovery | ❌ | 0 | NLP + rules |
| 2. Extraction | ❌ | 0 | GLiNER + GLiREL + regex |
| 3. Disambiguation | ✅ | ~2K | Resolve only what NLP can't |
| 4. Graph Assembly | ❌ | 0 | Code-driven |
| 5. Narrative | ✅ | ~4K | Interpret finished graph |
| **Total** | | **~6K tokens** | **2 API calls** |

## Features

- **Document Parsing**: PDF text extraction using `pdfplumber` with page-level tracking.
- **Entity & Relation Extraction**: GLiNER for typed entity recognition, GLiREL for relationship extraction.
- **Rule-Based Events**: Regex-driven extraction of targets, reductions, and quantitative observations.
- **Targeted LLM Disambiguation**: Sends only ambiguous sentences (~2K tokens) to resolve orphan values, ambiguous links, and unanchored pronouns.
- **V2 Graph Architecture**: Typed nodes (Entity, Observation, Target, Event) anchored to identified companies.
- **LLM Narrative**: Professional investor-grade summary generated from the structured graph.
- **Caching**: Save/load intermediate results for fast iteration.

## Setup

### Prerequisites
- Python 3.10+
- Google AI API key ([get one here](https://aistudio.google.com/apikey))

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

1. Create a `.env` file in the project root:
```
GOOGLE_API_KEY=your_api_key_here
```

2. The model defaults to `gemini-2.5-flash`. Change in `config.py` if needed.

## Usage

### Full Pipeline
```bash
python main.py path/to/report.pdf
```

### Skip LLM (NLP-only graph)
```bash
python main.py path/to/report.pdf --skip-llm
```

### Fast Iteration (LLM-Only)
First run with caching:
```bash
python main.py path/to/report.pdf --save-intermediates
```
Then iterate on LLM steps only:
```bash
python main.py path/to/report.pdf --llm-only
```

### Options
| Flag | Description |
|------|-------------|
| `--skip-llm` | Skip all LLM steps (stages 3 & 5) |
| `--save-intermediates` | Cache extraction results to `output/intermediates.json` |
| `--llm-only` | Load cached results, skip extraction models |
| `--relation-threshold` | Confidence threshold for relations (default: 0.08) |

## Outputs

| File | Description |
|------|-------------|
| `output/graph.graphml` | Full Knowledge Graph in GraphML format |
| `output/insights.md` | LLM-generated narrative summary |
| `output/nodes.csv` | Flat file of all graph nodes |
| `output/edges.csv` | Flat file of all graph edges |
| `output/observations.csv` | Extracted quantitative metrics |

## Visualization

```bash
python graph_viewer.py output/graph.graphml
```

## Project Structure

```
fact-forge/
├── main.py                    # Pipeline orchestrator
├── config.py                  # Model names, thresholds, ESG schemas
├── model_loader.py            # NLP model loading (spaCy, GLiNER, etc.)
├── graph_viewer.py            # Interactive graph visualization
├── requirements.txt
├── .env                       # Google AI API key (git-ignored)
│
├── parsers/                   # PDF parsing
├── discovery/                 # spaCy prescan, taxonomy discovery
├── classification/            # ESG topic & quantitative classification
├── extraction/                # Entity, relation, event extraction + LLM disambiguation
├── assembly/                  # Graph building, dedup, normalization, export
├── enrichment/                # Metadata enrichment, graph algorithms
├── insight/                   # LLM narrative generation
├── utils/                     # LLM client (Gemini API)
└── output/                    # Generated artifacts (git-ignored)
```
