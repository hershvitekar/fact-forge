# Fact Forge — ESG Knowledge Graph Pipeline v2.5 (Precision Architecture)

A high-fidelity regulatory engine for extracting Environmental, Social, and Governance (ESG) disclosures from PDF reports and building a structured Knowledge Graph (KG) compliant with global standards (**SEC, CSRD, SEBI BRSR**).

## 🚀 Architecture: Multi-Modal Alignment

The pipeline follows a **Regulatory-First, Precision-Hardened** philosophy. It aligns unstructured NLP extraction with structured table parsing using a semantic bridge.

```
PDF Document
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 1 — DISCOVERY & MAPPING                 │
│  • Structural Scaffolding  (spaCy/Docling)     │
│  • Regulatory Anchoring    (Sentence-EMB)      │
│  • ESG Pillar Strictness   (Taxonomy Map)      │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 2 — EXTRACTION (HYBRID)                 │
│  • Zero-Shot NER           (GLiNER)            │
│  • Relation Extraction     (GLiREL)            │
│  • High-Fidelity Tables    (Docling Markdown)  │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 3 — ASSEMBLY & PRECISION ALIGNMENT      │
│  • Context-Aware IDs       (Namespace Isolation)│
│  • Pillar-Strict Linking   (No Cross-Talk)     │
│  • MAPPED_TO Standards     (Regulatory Bridge) │
└────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────┐
│  STAGE 4 — EVALUATION & ANALYTICS              │
│  • Automated ESG Scorecard (13+ Standard Qs)   │
│  • Pillar-Aware Validation (Env/Soc/Gov)       │
│  • YoY Anomaly Detection   (Temporal Edges)    │
└────────────────────────────────────────────────┘
```

## ✨ Key Features

### 🏢 Context-Aware Namespace
Replaces generic metric names (e.g., "Total") with unique, context-aware IDs like `esg_metric_emissions_table_scope_1`. This prevents data from different tables from colliding into "monster nodes."

### 🛡️ Pillar-Strict Topology
Enforces a "Wall of Separation" between ESG pillars. The graph assembly engine prevents hallucinations by ensuring that a node discovered in an **Environmental** section cannot be mapped to a **Social** or **Governance** standard.

### 📊 Multi-Modal Table Extraction
Integrates **Docling** for industrial-grade table parsing. Structured table facts (Metric, Value, Unit, Year) are extracted from complex layouts and automatically tethered to standard regulatory indicators.

### 🔍 Semantic Regulatory Mapping
Uses **Transformer Embeddings** (Cosine Similarity) to map document headers to **13+ mandatory indicators** from:
- **India**: SEBI BRSR Essential Indicators.
- **USA**: SEC Climate-Related Disclosures.
- **EU**: CSRD / ESRS Requirements.

## 🛠️ Usage

### Full Pipeline
```bash
python main.py path/to/report.pdf
```

### Graph-Only Mode (Fast Assembly Tuning)
Load cached extraction results and re-run only the graph assembly and mapping logic.
```bash
python main.py path/to/report.pdf --graph-only
```

### Options
| Flag | Description |
|------|-------------|
| `--skip-llm` | Skip all LLM steps (stages 3 & 5) |
| `--save-intermediates` | Cache extraction results for fast iteration |
| `--graph-only` | Load cached extraction, tune graph assembly only |
| `--relation-threshold` | Confidence threshold for relations (default: 0.08) |

## 📈 Evaluation & Skills

Trigger specialized skills after a run to audit the graph:

- **ESG Evaluator**: `python eval_engine/evaluator.py graph.graphml`
  - Performs standard question answering against the KG.
- **Anomaly Detection**: `python eval_engine/anomaly_skill.py graph.graphml`
  - Flags YoY spikes and data contradictions.

## 📊 Knowledge Graph Schema

| Node Type | Purpose |
|-----------|---------|
| `Company` | The reporting entity. |
| `Standard ESG Metric` | Canonical regulatory indicator (e.g., `ENV_GHG_S1`). |
| `ESG Metric` | Specific fact found in document (Context-Aware). |
| `Quantitative Value` | The actual numeric disclosure. |
| `ESG Pillar` | Environmental, Social, or Governance parent node. |

| Edge Relation | Meaning |
|---------------|---------|
| `MAPPED_TO` | Links a document fact to a Regulatory Standard. |
| `MEASURES` | Links a Metric to its Numeric Value. |
| `HAS_PILLAR` | Enforces structural categorization. |
| `YEAR_OVER_YEAR` | Links temporal data points. |

## 🏗️ Project Structure

- `discovery/`: Semantic taxonomy and structural prescans.
- `extraction/`: GLiNER, GLiREL, and Docling table parser.
- `assembly/`: Contextual ID generation and regulatory bridging.
- `eval_engine/`: Regulatory question bank and evaluation logic.
- `output/`: GraphML, Insights, and CSV exports.
