"""
Targeted LLM Disambiguation — resolves only what NLP/code cannot.

Instead of sending the full document to the LLM, this module:
1. Scans NLP-extracted entities for gaps (orphan values, ambiguous links)
2. Collects only the problematic sentences (~20-40)
3. Sends a single, small LLM call (~2K tokens) to resolve ambiguities

The graph is built primarily by NLP + rules.  The LLM is used minimally
for coreference resolution and ambiguous metric-value linking.
"""

import logging
import json
import re

from utils.llm_client import query_llm


# ── Gap detection helpers ──────────────────────────────────────────────────────

def _find_orphan_values(entities, sentences, full_text):
    """
    Find Quantitative Value entities that have no nearby ESG Metric
    in the same sentence.  These are "orphans" that NLP extracted
    but couldn't anchor to a metric.

    Returns a list of dicts:
      {"sentence": str, "value": str, "nearby_entities": [str, ...]}
    """
    # Build a sentence lookup: for each entity, find which sentence it's in
    orphans = []

    # Index: map entity start offset → entity dict
    value_entities = [e for e in entities if e["label"] == "Quantitative Value"]
    metric_entities = [e for e in entities if e["label"] == "ESG Metric"]

    for val_ent in value_entities:
        val_start = val_ent["start"]
        val_end = val_ent["end"]

        # Find the sentence containing this value
        host_sentence = None
        for sent in sentences:
            sent_start = full_text.find(sent)
            if sent_start == -1:
                continue
            sent_end = sent_start + len(sent)
            if sent_start <= val_start < sent_end:
                host_sentence = sent
                break

        if not host_sentence:
            continue

        # Check if any ESG Metric entity is in the same sentence
        sent_start_in_doc = full_text.find(host_sentence)
        sent_end_in_doc = sent_start_in_doc + len(host_sentence)

        metrics_in_sentence = [
            m for m in metric_entities
            if sent_start_in_doc <= m["start"] < sent_end_in_doc
        ]

        if not metrics_in_sentence:
            # This value has no metric in its sentence — it's an orphan
            nearby = [e["text"] for e in entities
                      if sent_start_in_doc <= e["start"] < sent_end_in_doc
                      and e["label"] != "Quantitative Value"]
            orphans.append({
                "sentence": host_sentence.strip(),
                "value": val_ent["text"],
                "nearby_entities": nearby,
            })

    return orphans


def _find_ambiguous_links(entities, sentences, full_text):
    """
    Find sentences where multiple ESG Metrics co-occur with a
    Quantitative Value — NLP can't determine which metric the value
    belongs to.

    Returns a list of dicts:
      {"sentence": str, "value": str, "candidate_metrics": [str, ...]}
    """
    ambiguous = []
    value_entities = [e for e in entities if e["label"] == "Quantitative Value"]
    metric_entities = [e for e in entities if e["label"] == "ESG Metric"]

    for val_ent in value_entities:
        val_start = val_ent["start"]

        # Find host sentence
        host_sentence = None
        for sent in sentences:
            sent_start = full_text.find(sent)
            if sent_start == -1:
                continue
            sent_end = sent_start + len(sent)
            if sent_start <= val_start < sent_end:
                host_sentence = sent
                break

        if not host_sentence:
            continue

        sent_start_in_doc = full_text.find(host_sentence)
        sent_end_in_doc = sent_start_in_doc + len(host_sentence)

        metrics_in_sentence = [
            m["text"] for m in metric_entities
            if sent_start_in_doc <= m["start"] < sent_end_in_doc
        ]

        if len(metrics_in_sentence) >= 2:
            ambiguous.append({
                "sentence": host_sentence.strip(),
                "value": val_ent["text"],
                "candidate_metrics": metrics_in_sentence,
            })

    return ambiguous


def _find_unanchored_pronouns(sentences, main_company):
    """
    Find sentences with first-person pronouns ("we", "our") that contain
    ESG-relevant keywords.  These need coreference resolution to anchor
    to the main company.

    Returns a list of sentences (strings).
    """
    if not main_company:
        return []

    pronoun_re = re.compile(r'\b(we|our|us)\b', re.IGNORECASE)
    esg_signal_re = re.compile(
        r'\b(emissions?|energy|scope|renewable|carbon|target|commit|reduc|workforce|diversity)\b',
        re.IGNORECASE,
    )

    unanchored = []
    for sent in sentences:
        if pronoun_re.search(sent) and esg_signal_re.search(sent):
            # Only flag if the company name is NOT already explicit
            if main_company.lower() not in sent.lower():
                unanchored.append(sent.strip())

    # Cap at 30 sentences to keep token usage low
    return unanchored[:30]


# ── Main entry point ──────────────────────────────────────────────────────────

def resolve_ambiguities(document, entities, relations, main_company=None):
    """
    Targeted LLM disambiguation for the graph-building stage.

    Scans NLP-extracted entities for three types of gaps:
    1. Orphan values — numbers with no nearby metric
    2. Ambiguous links — values near multiple metrics
    3. Unanchored pronouns — "we/our" ESG claims needing company attribution

    Sends ONLY the problematic sentences to the LLM (~2K tokens),
    not the full document.  Returns the original relations list
    augmented with any LLM-resolved structured facts.
    """
    full_text = document.get("text", "")
    if not full_text:
        return relations

    company_name = main_company if main_company else "the company"

    # ── Detect gaps ────────────────────────────────────────────────────────────
    orphans = _find_orphan_values(entities, document.get("sentences", []), full_text)
    ambiguous = _find_ambiguous_links(entities, document.get("sentences", []), full_text)
    unanchored = _find_unanchored_pronouns(
        document.get("sentences", []), main_company
    )

    total_problems = len(orphans) + len(ambiguous) + len(unanchored)

    if total_problems == 0:
        logging.info("No disambiguation needed — NLP extraction is clean")
        return relations

    logging.info(
        "Found %d gaps to resolve: %d orphan values, %d ambiguous links, %d unanchored pronouns",
        total_problems, len(orphans), len(ambiguous), len(unanchored),
    )

    # ── Build a minimal, focused prompt ────────────────────────────────────────
    problem_blocks = []

    if orphans:
        lines = ["ORPHAN VALUES (no metric found nearby — identify the metric):"]
        for o in orphans[:15]:  # cap to control tokens
            lines.append(
                f'  - Value "{o["value"]}" in: "{o["sentence"]}"'
                f'  | Nearby entities: {o["nearby_entities"]}'
            )
        problem_blocks.append("\n".join(lines))

    if ambiguous:
        lines = ["AMBIGUOUS LINKS (value near multiple metrics — pick the correct one):"]
        for a in ambiguous[:10]:
            lines.append(
                f'  - Value "{a["value"]}" could be: {a["candidate_metrics"]}'
                f'  | Sentence: "{a["sentence"]}"'
            )
        problem_blocks.append("\n".join(lines))

    if unanchored:
        lines = [
            f'UNANCHORED PRONOUNS ("we/our" likely refers to {company_name}):',
        ]
        for s in unanchored[:15]:
            lines.append(f'  - "{s}"')
        problem_blocks.append("\n".join(lines))

    problems_text = "\n\n".join(problem_blocks)

    system_prompt = (
        "You are an ESG data resolver. You receive sentences where NLP extraction "
        "found gaps. Your job is to resolve ONLY the ambiguities listed below. "
        f'The main company in this report is "{company_name}". '
        "All first-person pronouns (we, our, us) refer to this company."
    )

    prompt = f"""Resolve these extraction gaps and return a JSON list of structured facts.

{problems_text}

For each resolved gap, output one JSON object with the appropriate type:

MetricObservation — when you can identify the metric for a value:
{{"type": "MetricObservation", "company": "{company_name}", "metric": "<name>", "value": "<number>", "unit": "<unit>", "year": <year or null>, "confidence": <0.0-1.0>}}

Event — when you identify a change or achievement:
{{"type": "Event", "company": "{company_name}", "event_type": "<Reduction|Increase|Achievement>", "value": "<value>", "year": <year or null>, "related_metric": "<metric>"}}

Target — when you identify a commitment:
{{"type": "Target", "company": "{company_name}", "target_type": "<description>", "target_year": <year>, "baseline_year": <year or null>}}

JSON OUTPUT (list of resolved facts only):"""

    response = query_llm(prompt, system_prompt=system_prompt, max_tokens=4096)
    resolved_facts = _parse_llm_response(response)

    logging.info(
        "LLM resolved %d facts from %d gaps (~%d prompt tokens)",
        len(resolved_facts), total_problems, len(prompt) // 4,
    )

    return relations + resolved_facts


def _parse_llm_response(response):
    """Safely extract and parse a JSON list from the LLM response."""
    if not response:
        return []

    try:
        content = response.strip()
        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        start_idx = content.find("[")
        if start_idx != -1:
            bracket_count = 0
            end_idx = -1
            for i in range(start_idx, len(content)):
                if content[i] == "[":
                    bracket_count += 1
                elif content[i] == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_idx = i
                        break

            if end_idx != -1:
                json_str = content[start_idx:end_idx + 1]
                return json.loads(json_str)
            else:
                json_str = content[start_idx:content.rfind("]") + 1]
                return json.loads(json_str)
    except Exception as e:
        logging.debug("Failed to parse LLM disambiguation response: %s", e)

    return []
