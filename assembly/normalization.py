import re

# Common ESG synonym mapping to canonical forms
ESG_SYNONYMS = {
    # Emissions
    r'\bghg\b': 'Emissions',
    r'\bgreenhouse gas\b': 'Emissions',
    r'\bco2\b': 'Emissions',
    r'\bco2e\b': 'Emissions',
    r'\bscope 1\b': 'Scope 1 Emissions',
    r'\bscope 2\b': 'Scope 2 Emissions',
    r'\bscope 3\b': 'Scope 3 Emissions',

    # Energy
    r'\brenewable energy\b': 'Renewable Energy',
    r'\bsolar\b': 'Renewable Energy',
    r'\bwind\b': 'Renewable Energy',
    r'\belectricity\b': 'Energy Usage',

    # Standards & Frameworks
    r'\bsdg\b': 'SDG',
    r'\bsdgs\b': 'SDG',
    r'\besrs\b': 'ESRS',
    r'\btcfd\b': 'TCFD',
    r'\bsasb\b': 'SASB',
    r'\bgri\b': 'GRI',

    # General terms
    r'\bnet zero\b': 'Net Zero',
    r'\bcarbon neutral\b': 'Carbon Neutrality',
}

# Unit canonicalization
UNIT_MAPPING = {
    r'\b(tonnes?|tons?|tco2e?)\b': 'tCO2e',
    r'\b(mwh|megawatt.hours?)\b': 'MWh',
    r'\b(gwh|gigawatt.hours?)\b': 'GWh',
    r'\b%\b': '%',
}

# Entities to ignore (stop-entities)
STOP_ENTITIES = {
    'we', 'us', 'our', 'it', 'they', 'them', 'their', 'everyone', 'all',
    'undertaking', 'company', 'organization', 'group', 'entity', 'this', 'that',
    'report', 'disclosure', 'information', 'data', 'year', 'period',
    'might', 'could', 'would', 'should', 'can', 'may', 'must', 'will',
    'also', 'many', 'some', 'any', 'such', 'these', 'those'
}

# ── Task 1: PDF Artifact Filtering ─────────────────────────────────────────────
# Known reverse-text / garbled PDF header artifacts from the Spotify report
PDF_ARTIFACTS = {
    "EDIRP", "NOBRAC", "KEEW", "SELCRIC", "ORFA", "AFROSWEDE",
    "NLP",  # "Nlp" detected as Company — pipeline artifact from module name
    "WE COMPANY", "OUR COMPANY", "WE", "OUR",
}

# Pattern: word where every consecutive pair of chars is the same (e.g. "RReeppoorrtt")
_DOUBLE_CHAR_RE = re.compile(r'^(.)\1(.)\2(.)\3', re.IGNORECASE)


def _is_double_encoded(text: str) -> bool:
    """Detect strings like 'RReeppoorrtt' from double-encoded PDFs."""
    # Strip spaces and check if first 6+ chars are pairwise equal
    t = text.replace(" ", "")
    if len(t) < 6:
        return False
    return all(t[i] == t[i + 1] for i in range(0, min(6, len(t) - 1), 2))


def should_filter_entity(text: str) -> bool:
    """Return True if entity should be excluded from the graph."""
    if not text:
        return True
    t = text.strip()
    norm = t.lower()

    # Stop-entities list
    if norm in STOP_ENTITIES or len(norm) <= 1:
        return True

    # Pure numbers
    if norm.isdigit():
        return True

    # Known PDF artifact strings (case-insensitive)
    if t.upper() in PDF_ARTIFACTS:
        return True

    # Double-encoded characters (e.g. "EEqquuiittyy", "RReeppoorrtt")
    if _is_double_encoded(t):
        return True

    # ALL-CAPS short tokens with no ESG meaning (≤5 chars, not a known acronym)
    KNOWN_CAPS_ALLOWED = {
        "TCFD", "SASB", "GRI", "SDG", "ESG", "GHG", "IEA", "EAC",
        "PULSE", "GLOW", "EQUAL", "EDI", "CEF", "SSAC", "SCOC", "FAR",
        "BLK", "MSA", "CEO", "CFO", "CHRO", "EU", "UK", "US", "UN",
    }
    if t.isupper() and len(t) <= 6 and t not in KNOWN_CAPS_ALLOWED:
        return True

    return False


# ── Task 7: Entity Type Reclassification ──────────────────────────────────────
# Internal tools/programs that GLiNER misclassifies as "Company"
ENTITY_TYPE_OVERRIDES = {
    "echo":                "Internal Tool",
    "greenhouse":          "Internal Tool",
    "all the feels":       "Internal Program",
    "heart & soul":        "Internal Program",
    "benevity":            "Platform",
    "read&write":          "Platform",
    "dimpact":             "Partnership",
    "mentivity":           "Partnership",
    "norrsken":            "Partnership",
    "colorintech":         "Partnership",
    "adcolor":             "Partnership",
    "good energy":         "Partnership",
    "the platform rules":  "Policy Document",
    "whistleblower policy":"Policy Document",
    "our greenhouse learning platform": "Internal Tool",
}

# Regex for "First Last" person name pattern
_PERSON_NAME_RE = re.compile(r'^[A-Z][a-z]+ [A-Z][a-z]+$')


def reclassify_entity_label(text: str, label: str) -> str:
    """Override misclassified entity labels based on known patterns."""
    t = text.strip()
    t_lower = t.lower()

    # Check explicit overrides first
    if t_lower in ENTITY_TYPE_OVERRIDES:
        return ENTITY_TYPE_OVERRIDES[t_lower]

    # Reclassify apparent person names from Company -> Person
    if label == "Company" and _PERSON_NAME_RE.match(t):
        return "Person"

    return label


# ── Existing normalization helpers ────────────────────────────────────────────
def normalize_text(text, label=None):
    """Normalize text by lowercasing, stripping, and mapping synonyms/units."""
    if not text:
        return ""
    if isinstance(text, list):
        text = " ".join(str(x) for x in text)

    # Basic cleanup
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)

    has_digits = any(char.isdigit() for char in text)

    # Apply unit mapping
    for pattern, canonical in UNIT_MAPPING.items():
        if re.search(pattern, text):
            if has_digits or label == "Quantitative Value":
                text = re.sub(pattern, canonical, text)
            else:
                return canonical

    # Apply synonym mapping
    for pattern, canonical in ESG_SYNONYMS.items():
        if re.search(pattern, text):
            if has_digits and "scope" not in pattern.lower() and "co2" not in pattern.lower():
                # Don't obliterate strings with numbers unless it's a known metric with numbers
                text = re.sub(pattern, canonical, text)
            else:
                return canonical.strip()

    return text.title()  # Return title case for display if no synonym found
