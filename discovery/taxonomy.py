import logging
import re

ESG_KEYWORDS = {
    "environment": ["climate", "carbon", "emissions", "energy", "water", "waste", "biodiversity", "environmental"],
    "social": ["human rights", "diversity", "inclusion", "employees", "safety", "community", "labor", "social"],
    "governance": ["board", "ethics", "corruption", "transparency", "governance", "audit", "compliance", "risk management"],
    "strategy": ["business model", "strategy", "transition", "resilience"],
    "targets": ["net zero", "reduction target", "commitment", "goal", "objective"],
}

def discover_taxonomy(document, prescan):
    """Discover ESG taxonomy signals and sections from the document."""
    logging.info("Discovering taxonomy from document")
    text = document.get("text", "").lower()
    
    found_categories = {}
    for cat, keywords in ESG_KEYWORDS.items():
        count = 0
        for kw in keywords:
            count += len(re.findall(r'\b' + re.escape(kw) + r'\b', text))
        if count > 0:
            found_categories[cat] = count

    # Identify potential sections based on sentence structure or headings
    # For now, we'll just look for common section names in the sentences
    sections = []
    common_sections = ["introduction", "environmental impact", "social responsibility", "corporate governance", "appendix"]
    
    for section_name in common_sections:
        if re.search(r'\b' + re.escape(section_name) + r'\b', text):
            sections.append({"name": section_name, "score": 1.0})

    return {
        "categories": list(found_categories.keys()),
        "category_counts": found_categories,
        "sections": sections,
    }
