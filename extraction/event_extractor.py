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
    """Return all numeric values found in a sentence with their units."""
    results = []
    for m in _NUMBER_RE.finditer(sentence):
        raw_val = m.group(1)
        unit = m.group(2) or ""
        if not raw_val:
            continue
        # Normalise: strip commas and currency symbols
        clean_val = raw_val.replace(",", "").replace("$", "").strip()
        results.append({"value": clean_val, "unit": unit.strip(), "raw": m.group(0).strip()})
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
    using rule-based patterns with numeric pre-extraction.

    Returns a list of structured fact dicts compatible with graph_builder.py.
    """
    logging.info("Extracting ESG events from %d sentences", len(sentences))
    events = []

    comparator_pattern = "|".join(config.QUANT_COMPARATORS)
    temporal_pattern = "|".join(config.QUANT_TEMPORAL)

    for sentence in sentences:
        # ── Determine event type ───────────────────────────────────────────────
        has_comparator = bool(re.search(comparator_pattern, sentence, re.IGNORECASE))
        has_temporal   = bool(re.search(temporal_pattern, sentence, re.IGNORECASE))

        if not (has_comparator or has_temporal):
            # Still check for commitments/targets below
            pass
        else:
            event_type = "Observation"
            if re.search(r'\breduc(e|ed|ing|tion)\b', sentence, re.IGNORECASE):
                event_type = "Reduction"
            elif re.search(r'\bincreas(e|ed|ing)\b', sentence, re.IGNORECASE):
                event_type = "Increase"
            elif re.search(r'\bdecreas(e|ed|ing)\b', sentence, re.IGNORECASE):
                event_type = "Reduction"

            # ── Task 3 core: numeric pre-extraction ───────────────────────────
            numbers = _extract_numbers(sentence)

            # Find percentage first (most specific for ESG events)
            pct_match = re.search(r'(\d+(?:\.\d+)?\s?%)', sentence)

            if pct_match:
                value = pct_match.group(1).strip()
                unit  = "%"
                subject = _best_subject(sentence, pct_match.start())
            elif numbers:
                # Use first numeric value found
                best = numbers[0]
                value   = best["value"]
                unit    = best["unit"]
                subject = _best_subject(sentence, sentence.find(best["raw"]))
            else:
                value   = "unknown"
                unit    = ""
                subject = "Metric"

            # Year extraction
            year_m = re.search(r'\b(20\d{2})\b', sentence)
            year   = year_m.group(1) if year_m else None

            # Only emit event if we have a real value OR a clear direction
            if value != "unknown" or event_type != "Observation":
                events.append({
                    "type":       "Event",
                    "event_type": event_type,
                    "metric":     subject,
                    "value":      value,
                    "unit":       unit,
                    "year":       year,
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
        # Captures sentences with clear metric+value pairs (e.g., GHG tables)
        if not has_comparator and not is_commitment:
            numbers = _extract_numbers(sentence)
            esg_hint = _ESG_SUBJECT_HINTS.search(sentence)
            if numbers and esg_hint:
                best    = numbers[0]
                year_m  = re.search(r'\b(20\d{2})\b', sentence)
                events.append({
                    "type":       "Event",
                    "event_type": "Observation",
                    "metric":     esg_hint.group(0).strip(),
                    "value":      best["value"],
                    "unit":       best["unit"],
                    "year":       year_m.group(1) if year_m else None,
                    "context":    sentence.strip(),
                })

    logging.info("Extracted %d events/targets via rules", len(events))
    return events
