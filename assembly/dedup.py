import logging
from difflib import SequenceMatcher
from typing import List, Dict

# ── Label groups for fuzzy dedup scope ────────────────────────────────────────
# Only merge nodes within the same group — never merge a Company with a Metric
LABEL_GROUPS = {
    "env":  {"ESG Metric", "Sustainability Framework"},
    "quant": {"Quantitative Value", "Unit of Measure"},
    "org":  {"Company", "Person", "Partnership", "Platform", "Internal Tool", "Internal Program"},
    "time": {"Reporting Year"},
    "policy": {"Policy Document"},
}

FUZZY_THRESHOLD = 0.72   # Jaccard/sequence similarity cutoff for merging


def _label_group(label: str) -> str:
    """Return the group key for a given label, or the label itself if unknown."""
    for group, labels in LABEL_GROUPS.items():
        if label in labels:
            return group
    return label  # treat unknown labels as their own singleton group


def _token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on lowercase word-token sets."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio on lowercased strings (handles substrings well)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _similarity(a: str, b: str) -> float:
    """Combined similarity: max of Jaccard and sequence ratio."""
    return max(_token_jaccard(a, b), _sequence_similarity(a, b))


def deduplicate_entities(entities: List[Dict]) -> List[Dict]:
    """
    Deduplicate entities using fuzzy similarity within label groups.

    Strategy:
    1. Exact (text, label) dedup first (fast path).
    2. Within each label group, pairwise similarity check.
       If similarity > FUZZY_THRESHOLD, keep the higher-scored entity.
    """
    if not entities:
        return entities

    logging.info("Deduplicating %d entities (fuzzy threshold=%.2f)", len(entities), FUZZY_THRESHOLD)

    # ── Step 1: Exact match dedup ──────────────────────────────────────────────
    seen_exact: dict = {}
    for ent in entities:
        key = (ent["text"].lower().strip(), ent.get("label", ""))
        if key not in seen_exact or ent.get("score", 0) > seen_exact[key].get("score", 0):
            seen_exact[key] = ent
    candidates = list(seen_exact.values())

    # ── Step 2: Fuzzy dedup within label groups ────────────────────────────────
    # Group by label group
    groups: dict[str, List[Dict]] = {}
    for ent in candidates:
        g = _label_group(ent.get("label", "unknown"))
        groups.setdefault(g, []).append(ent)

    survivors: List[Dict] = []
    for group_name, group_ents in groups.items():
        # Skip groups that don't benefit from fuzzy merge (units, time, quant)
        if group_name in ("quant", "time", "unit"):
            survivors.extend(group_ents)
            continue

        # Greedy merge: iterate and mark duplicates
        merged = [True] * len(group_ents)  # True = still alive
        for i in range(len(group_ents)):
            if not merged[i]:
                continue
            for j in range(i + 1, len(group_ents)):
                if not merged[j]:
                    continue
                sim = _similarity(group_ents[i]["text"], group_ents[j]["text"])
                if sim >= FUZZY_THRESHOLD:
                    # Keep the one with higher score
                    if group_ents[j].get("score", 0) > group_ents[i].get("score", 0):
                        merged[i] = False  # i gets replaced by j
                        break             # i is gone; stop inner loop
                    else:
                        merged[j] = False  # j is a duplicate of i

        survivors.extend([e for e, alive in zip(group_ents, merged) if alive])

    logging.info("Dedup complete: %d → %d entities", len(entities), len(survivors))
    return survivors
