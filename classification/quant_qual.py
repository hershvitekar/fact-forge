import logging
import re
import config

def extract_quant_qual(document):
    """Extract quantitative and qualitative signals from the parsed document."""
    logging.info("Extracting quantitative and qualitative signals")
    text = document.get("text", "")
    
    quant_signals = []
    qual_signals = []
    
    # Quantitative detection: look for units and numbers
    for unit_pattern in config.QUANT_UNITS:
        matches = re.finditer(r'(\d+(?:\.\d+)?)\s*' + unit_pattern, text, re.IGNORECASE)
        for match in matches:
            quant_signals.append(f"{match.group(1)} {match.group(2)}")
            
    # Qualitative detection: look for comparators and temporal signals
    for comp_pattern in config.QUANT_COMPARATORS:
        if re.search(comp_pattern, text, re.IGNORECASE):
            qual_signals.append(f"Trend signal: {comp_pattern}")
            
    for temp_pattern in config.QUANT_TEMPORAL:
        if re.search(temp_pattern, text, re.IGNORECASE):
            qual_signals.append(f"Temporal signal: {temp_pattern}")

    return {
        "quantitative": list(set(quant_signals)),
        "qualitative": list(set(qual_signals)),
    }
