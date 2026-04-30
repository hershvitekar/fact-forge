import json
import os

with open('scratch_analysis.json', 'r') as f:
    results = json.load(f)

insights = [
    {
        'title': 'Insight 1: Climate Goals & Emissions',
        'text': 'Spotify continues to make measurable progress toward its ambitious climate goals, anchored by a commitment to reach Net Zero by 2030. In 2024, the company achieved a reduction in its location-based Scope 2 emissions, which fell to 3,954 tCO2e from 4,178 tCO2e in 2023. This downward trend is supported by a broader 7% reduction in total greenhouse gas (GHG) emissions. Efficiency gains are particularly evident in the company’s operational scaling; in 2023, Spotify reported a 41% decrease in emissions per million users. While energy consumption across categories such as fuel and electricity saw fluctuations—with specific usage metrics shifting from 1,263 to 1,837 in certain segments—the company remains focused on decarbonizing its value chain. Market-based Scope 2 emissions currently represent 4.2% of the total footprint, and the company is actively utilizing carbon credits and targeted learning materials in key markets like Stockholm and Berlin to further mitigate its environmental impact.',
        'terms': ['Net Zero', '2030', '3,954', '4,178', '7%', 'greenhouse gas', 'GHG', '41%', 'million users', '1,263', '1,837', '4.2%', 'Market-based', 'Stockholm', 'Berlin']
    },
    {
        'title': 'Insight 2: Workplace Culture & Diversity',
        'text': 'The "bandmate" culture at Spotify remains a core strategic asset, characterized by high engagement and a strong sense of purpose. In October 2024, Spotify achieved an 87% response rate in its internal engagement surveys, with employees reporting a pride-of-work score of 84 out of 100. The company’s commitment to diversity and inclusion is reflected in its workforce composition, where women represent 42.8% of the global population and 4.2% identify as another gender. Spotify has also seen success in its internal mobility and talent development programs; 6.6% of full-time employees utilized "Echo," the company’s AI-powered internal talent marketplace, to explore new opportunities. Furthermore, Spotify continues to expand its reach within the creative community, increasing the representation of students, professionals, and songwriters from 14.1% in 2022 to 19.5% in 2023. Employee well-being remains a priority, with 79% of staff accessing mental health resources and 53.0% of eligible employees taking parental leave during the reporting period.',
        'terms': ['87%', 'response rate', '84', '100', 'pride', '42.8%', '6.6%', 'Echo', '14.1%', '19.5%', '79%', 'mental health', '53.0%', 'parental leave']
    },
    {
        'title': 'Insight 3: Governance & Creator Support',
        'text': 'Governance at Spotify is centered on fostering transparency and creating long-term value for the global creator ecosystem. The company’s "Spotlight" initiative, designed to improve awareness and understanding of corporate standards, achieved a perfect score of 100, reflecting a deeply embedded culture of accountability. Spotify’s governance framework supports multi-year initiatives like the Creator Equity Fund, which aims to generate longer-lasting value for artists and creators. By integrating ESG metrics into its core business strategy, Spotify ensures that its pursuit of streaming growth is balanced with ethical oversight and a commitment to its 2030 Net Zero roadmap.',
        'terms': ['Spotlight', 'Creator Equity Fund']
    }
]

with open('insight_graph_analysis.md', 'w', encoding='utf-8') as f:
    f.write('# Insight Graph Analysis\n\n')
    f.write('This report maps the generated LLM insights back to specific nodes and edges found in the underlying knowledge graph (`output/graph.graphml`).\n\n')
    
    for insight in insights:
        f.write(f'## {insight["title"]}\n')
        f.write(f'> {insight["text"]}\n\n')
        f.write('### Graph Evidence:\n')
        
        found_any = False
        for term in insight['terms']:
            matches = results.get(term, [])
            if matches:
                found_any = True
                f.write(f'- **"{term}"** found in:\n')
                # Deduplicate based on node ID/edge
                seen = set()
                for match in matches:
                    if match['type'] == 'node':
                        node_id = match['id']
                        if node_id not in seen:
                            seen.add(node_id)
                            node_text = match['data'].get('text', '').replace('\n', ' ')
                            node_label = match['data'].get('label', '')
                            f.write(f'  - Node `{node_id}` (Label: {node_label}, Text: "{node_text}")\n')
                    elif match['type'] == 'edge':
                        edge_key = f"{match['source']}->{match['target']}"
                        if edge_key not in seen:
                            seen.add(edge_key)
                            edge_label = match['data'].get('label', '')
                            f.write(f'  - Edge from `{match["source"]}` to `{match["target"]}` (Label: {edge_label})\n')
        if not found_any:
            f.write('- *No direct matches found in the graph for the specific terms.*\n')
        f.write('\n')
