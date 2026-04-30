import re
import logging
import config

# ── Task 3: Numeric pre-extraction ────────────────────────────────────────────
# Captures: "190,596", "97.7%", "1,069 tCO2e", "11.4B", "$6 million"
_NUMBER_RE = re.compile(
    r'(\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:B|M|K)?)'   # number with optional suffix
    r'\s*'
    r'(%|tCO2e?|tCO₂e|MWh|GWh|kWh|MAUs?|million|billion|'
    r'impressions?|hours?|streams?|bandmates?|employees?)?',
    re.IGNORECASE,
)

# ESG subject keywords that appear near numbers
_ESG_SUBJECT_HINTS = re.compile(
    r'\b(scope\s*[123]|emissions?|energy|electricity|ghg|carbon|'
    r'employees?|bandmates?|women|men|non.?binary|parental|'
    r'streams?|users?|maus?|impressions?|donations?|fund)\b',
    re.IGNORECASE,
)

# Net-zero / target patterns
_NET_ZERO_RE = re.compile(
    r'\b(net.?zero|carbon.?neutral|net zero emissions?)\b', re.IGNORECASE
)


def _extract_numbers(sentence: str) -> list[dict]:
    """
    Return all numeric values found in a sentence with their units.
    Enforces strict proximity anchoring: A number is invalid unless anchored to
    A) A unit (either attached or in radius) AND B) A Date/Year in radius.
    """
    results = []
    for m in _NUMBER_RE.finditer(sentence):
        raw_val = m.group(1)
        unit = m.group(2) or ""
        if not raw_val:
            continue
            
        # Extract a 60-character radius (~10 tokens) around the number
        start_idx = max(0, m.start() - 60)
        end_idx = min(len(sentence), m.end() + 60)
        radius_text = sentence[start_idx:end_idx]
        
        # STRICT RULE B: Must have a Date/Year in the radius
        year_m = re.search(r'\b(20\d{2})\b', radius_text)
        if not year_m:
            continue  # Discard floating numbers with no year
            
        year = year_m.group(1)
        
        # STRICT RULE A: Must have a known Unit in the radius (if not attached)
        if not unit:
            found_unit = ""
            for unit_pattern in config.QUANT_UNITS:
                unit_m = re.search(unit_pattern, radius_text, re.IGNORECASE)
                if unit_m:
                    found_unit = unit_m.group(0)
                    break
            
            if not found_unit:
                continue  # Discard numbers with no unit
            unit = found_unit

        # Normalise: strip commas and currency symbols
        clean_val = raw_val.replace(",", "").replace("$", "").strip()
        results.append({
            "value": clean_val, 
            "unit": unit.strip(), 
            "year": year,
            "raw": m.group(0).strip(),
            "start": m.start()
        })
    return results


def _best_subject(sentence: str, value_match_start: int) -> str:
    """
    Heuristic: find the closest ESG subject keyword before the numeric value,
    then grab up to 4 words around it as the metric name.
    Falls back to last 4 words before the value.
    """
    prefix = sentence[:value_match_start].strip()

    # Prefer ESG-hint keyword as anchor
    hint_match = None
    for m in _ESG_SUBJECT_HINTS.finditer(prefix):
        hint_match = m  # last match is closest to the value

    if hint_match:
        # Take up to 3 words ending at the hint
        words_before = prefix[: hint_match.end()].split()
        return " ".join(words_before[-4:])

    # Fallback: last 4 words of prefix
    words = prefix.split()
    return " ".join(words[-4:]) if words else "Metric"


def extract_events(sentences: list[str]) -> list[dict]:
    """
    Extract ESG events (reductions, increases, commitments, observations)
    using strict proximity anchoring for numeric values.
    """
    logging.info("Extracting ESG events from %d sentences", len(sentences))
    events = []

    comparator_pattern = "|".join(config.QUANT_COMPARATORS)
    temporal_pattern = "|".join(config.QUANT_TEMPORAL)

    for sentence in sentences:
        # ── Determine event type ───────────────────────────────────────────────
        has_comparator = bool(re.search(comparator_pattern, sentence, re.IGNORECASE))
        has_temporal   = bool(re.search(temporal_pattern, sentence, re.IGNORECASE))

        if has_comparator or has_temporal:
            event_type = "Observation"
            if re.search(r'\breduc(e|ed|ing|tion)\b', sentence, re.IGNORECASE):
                event_type = "Reduction"
            elif re.search(r'\bincreas(e|ed|ing)\b', sentence, re.IGNORECASE):
                event_type = "Increase"
            elif re.search(r'\bdecreas(e|ed|ing)\b', sentence, re.IGNORECASE):
                event_type = "Reduction"

            # Use strict numeric extraction
            numbers = _extract_numbers(sentence)
            
            for num_data in numbers:
                subject = _best_subject(sentence, num_data["start"])
                events.append({
                    "type":       "Event",
                    "event_type": event_type,
                    "metric":     subject,
                    "value":      num_data["value"],
                    "unit":       num_data["unit"],
                    "year":       num_data["year"],
                    "context":    sentence.strip(),
                })

        # ── Commitments / net-zero targets ────────────────────────────────────
        is_commitment = bool(
            re.search(r'\b(commit|target|goal|aim|pledge|by\s+20\d{2})\b', sentence, re.IGNORECASE)
        )
        is_net_zero = bool(_NET_ZERO_RE.search(sentence))

        if is_commitment or is_net_zero:
            year_m = re.search(r'\b(20\d{2})\b', sentence)
            if year_m:
                target_type = "Net Zero" if is_net_zero else "Commitment"
                events.append({
                    "type":        "Target",
                    "target_type": target_type,
                    "target_year": year_m.group(1),
                    "context":     sentence.strip(),
                })

        # ── Numeric-only observations (no comparator needed) ──────────────────
        if not has_comparator and not is_commitment:
            numbers = _extract_numbers(sentence)
            esg_hint = _ESG_SUBJECT_HINTS.search(sentence)
            
            # Since numbers are strictly validated, we just need an ESG context hint to emit an observation
            if numbers and esg_hint:
                metric_name = esg_hint.group(0).strip()
                for num_data in numbers:
                    events.append({
                        "type":       "Event",
                        "event_type": "Observation",
                        "metric":     metric_name,
                        "value":      num_data["value"],
                        "unit":       num_data["unit"],
                        "year":       num_data["year"],
                        "context":    sentence.strip(),
                    })

    logging.info("Extracted %d events/targets via strict proximity rules", len(events))
    return events
