from pathlib import Path

# ── Core Paths & Observability ────────────────────────────────────────────────
INDEX_STORAGE_PATH = Path("data/indices")
LANGCHAIN_PROJECT = "fact-forge-esg"

# ── LLM Backend (Google Gemini) ───────────────────────────────────────────────
# API key is read from the GOOGLE_API_KEY environment variable.
GEMINI_MODEL = "gemini-3-flash-preview"

# Legacy: local llama.cpp server (no longer used)
# LLM_URL = "http://192.168.1.18:8080"
GLINER_MODEL = "urchade/gliner_medium-v2.1"
GLIREL_MODEL = "jackboyla/glirel-large-v0"
ESGBERT_MODEL = "ESGBERT/EnvironmentalBERT-environmental"
SENTENCE_TRANSFORMER = "all-MiniLM-L6-v2"
SPACY_MODEL = "en_core_web_trf"

GLINER_CONFIDENCE = 0.5
# ── Task 6: Lowered from 0.1 → 0.08 to surface more GLiREL relations ─────────
GLIREL_CONFIDENCE = 0.08
SEMANTIC_SIMILARITY_THRESHOLD = 0.75
FUZZY_MATCH_THRESHOLD = 0.85
SECTION_RANK_CUTOFF_PERCENTILE = 50

# Granularity settings
RELATION_PARA_SENTENCES = 4  # Paragraph size for relations (3-5 sentences)
ENTITY_BATCH_SIZE = 16       # Number of sentences to process at once for GLiNER


# === Quantitative classifier signals ===
QUANT_UNITS = [
    r'\b(tonnes?|metric tonnes?|tCO2e?|mtCO2e|MMT|MWh|GWh|kWh|GJ|TJ|gigajoules?|terajoules?|megajoules?|MJ)\b',
    r'\b(cubic\s?met[er]+s?|hectares?|litres?|liters?|gallons?|megalitr[e]+s?|megalit[er]s?)\b',
    r'\b(kg|kilograms?|grams?|lbs|pounds?)\b',
    r'[\$\xA3\u20AC\xA5]', # Currency symbols: $, £, €, ¥
    r'\b(USD|GBP|EUR|JPY|CHF|CAD|AUD|INR|dollars?|euros?|pounds?|yen|rupees?)\b',
    r'%|percent(age)?\b', 
    r'\b(billion|million|thousand|bn|m|k)\b', # Scale markers
    r'\b(rate|ratio|index|score|points|level|intensity|volume|quantity|share|proportion|count|number)\b', # ESG performance units
    r'\b(employees?|workers?|full-time equivalents?|fte)\b', # Social/Human Capital units
]





QUANT_COMPARATORS = [
    r'\b(increased?|decreased?|reduced?|grew|declined?|rose|fell)\b',
    r'\b(improved|worsened|expanded|contracted|doubled|tripled)\b',
]

QUANT_TEMPORAL = [
    r'\b(year.over.year|YoY|y-o-y|baseline|compared\s+to)\b',
    r'\b(since\s+\d{4}|vs\.?\s+\d{4}|from\s+\d{4})\b',
    r'\b(quarter.over quarter|QoQ|month.over.month)\b',
]

# ESG entity types (base taxonomy for V2)
BASE_ESG_ENTITY_TYPES = [
    "Company",
    "ESG Metric",
    "Unit of Measure",
    "Reporting Year",
    "Quantitative Value",
    "Sustainability Framework",
]

# ── Task 6: Expanded GLiREL relation labels with natural-language descriptions ─
# GLiREL uses the label description as a soft prompt — richer descriptions fire
# more often on ESG text patterns.
ESG_RELATION_LABELS = {
    "measured_as": {
        "description": "a metric or ESG indicator is measured as a specific numeric value",
        "allowed_head": ["ESG Metric"],
        "allowed_tail": ["Quantitative Value"],
    },
    "has_unit": {
        "description": "a quantity or measurement has a unit of measure such as tCO2e, MWh, or percent",
        "allowed_head": ["ESG Metric", "Quantitative Value"],
        "allowed_tail": ["Unit of Measure"],
    },
    "reported_at": {
        "description": "an ESG metric or value is reported for a specific year or time period",
        "allowed_head": ["ESG Metric", "Quantitative Value"],
        "allowed_tail": ["Reporting Year"],
    },
    "belongs_to": {
        "description": "an ESG metric, framework, or initiative belongs to or is part of a company or organisation",
        "allowed_head": ["ESG Metric", "Sustainability Framework"],
        "allowed_tail": ["Company"],
    },
    "measures": {
        "description": "a company reports or measures a specific ESG metric such as emissions, diversity, or energy",
        "allowed_head": ["Company"],
        "allowed_tail": ["ESG Metric", "Quantitative Value"],
    },
    "reduces": {
        "description": "a company, initiative, or action reduces an emission level or environmental metric",
        "allowed_head": ["Company", "Sustainability Framework"],
        "allowed_tail": ["ESG Metric", "Quantitative Value"],
    },
    "targets": {
        "description": "a company has set a goal, target, or commitment for a metric by a future year",
        "allowed_head": ["Company"],
        "allowed_tail": ["ESG Metric", "Sustainability Framework"],
    },
    "partners_with": {
        "description": "a company partners or collaborates with another organisation or initiative",
        "allowed_head": ["Company"],
        "allowed_tail": ["Company", "Sustainability Framework"],
    },
    "achieves": {
        "description": "a company achieves a score, rating, certification, or index result",
        "allowed_head": ["Company"],
        "allowed_tail": ["Quantitative Value", "ESG Metric"],
    },
    "aligns_with": {
        "description": "a company or report aligns with or follows a sustainability framework or reporting standard",
        "allowed_head": ["Company"],
        "allowed_tail": ["Sustainability Framework"],
    },
}
