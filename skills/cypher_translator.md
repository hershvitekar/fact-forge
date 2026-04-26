# 🧬 Skill: FactForge Cypher Translator (Kùzu Optimized)

This skill enables the AI to translate natural language into high-fidelity Kùzu Cypher queries for the ESG Knowledge Graph.

## 🏗️ Core Schema Knowledge
### Node Tables & Properties
- **Company**: `id`, `text`, `context`
- **ESG_Metric**: `id`, `text`, `context`
- **Quantitative_Value**: `id`, `text`, `value_float`, `context`
- **Target**: `id`, `text`, `context`, `year`
- **ESG_Pillar**: `id`, `text`
- **Reporting_Year**: `id`, `text`
- **Unit_of_Measure**: `id`, `text`

### Relationship Tables (Triple Underscore Schema)
- Pattern: `RELATION___SOURCE___TARGET`
- Examples: `MEASURES___ESG_Metric___Quantitative_Value`, `REPORTS_METRIC___Company___ESG_Metric`, `HAS_TARGET___Company___Target`

## ⚖️ Critical Syntax Rules (The "Kùzu Way")
1. **Relationship Check**: NEVER use `type(rel)`. ALWAYS use `label(rel)`.
2. **Multi-Label MATCH**: NEVER use the pipe operator (e.g., `MATCH (n:A|B)`). This causes parser exceptions. ALWAYS use `UNION ALL` to combine queries from different tables.
3. **Robust Filtering**: Use `WHERE label(r) CONTAINS 'REL_NAME'` instead of hardcoded table names to handle multi-modal edges.
3. **Property Access**: 
   - Use `.text` for names/headlines.
   - Use `.context` for narrative details and table rows.
   - Use `.value_float` for numeric comparisons (e.g., `WHERE v.value_float > 100`).
4. **String Searching**: Kùzu `CONTAINS` is case-sensitive. Use `lower(n.text) CONTAINS 'keyword'` for maximum recall.

## 🧩 Common Query Patterns
### 1. Narrative Discovery (The "How/Why")
```cypher
MATCH (n:Target|ESG_Metric|Sustainability_Framework)
WHERE lower(n.text) CONTAINS 'keyword'
RETURN n.text, n.context
```

### 2. Quantitative Performance (The "Numbers")
```cypher
MATCH (m:ESG_Metric)-[r1]->(v:Quantitative_Value)-[r2]->(y:Reporting_Year)
WHERE label(r1) CONTAINS 'MEASURES' AND label(r2) CONTAINS 'reported_at'
RETURN m.text, v.value_float, y.id
ORDER BY y.id DESC
```

### 3. Pillar Drilldown (The "ESG Filter")
```cypher
MATCH (p:ESG_Pillar)<-[r1]-(m:ESG_Metric)-[r2]->(v:Quantitative_Value)
WHERE p.id = 'pillar_environmental' 
  AND label(r1) CONTAINS 'CATEGORIZED_AS'
RETURN m.text, v.text
```
