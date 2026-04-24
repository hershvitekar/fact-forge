import pandas as pd
import re
import logging
from pathlib import Path

# Expanded Stop Words
STOP_WORDS = {
    'we', 'us', 'our', 'it', 'they', 'them', 'their', 'everyone', 'all',
    'company', 'organization', 'group', 'entity', 'this', 'that', 'report',
    'disclosure', 'data', 'information', 'year', 'period', 'might', 'could',
    'also', 'many', 'some', 'any', 'such', 'these', 'those', 'the', 'an', 'a',
    'our business', 'this report', 'the group', 'our commitment', 'the company',
    'we also', 'we have', 'we continue', 'we are', 'we seek', 'we work',
    'our operations', 'our people', 'our sustainability', 'our global',
    'the following', 'the additional', 'the accounting', 'the disclosure',
    'wedonot', 'weimplement', 'wealso', 'wehave', 'wework', 'wegenerate',
    'welook', 'weseek', 'newsuppliers', 'wecontinue', 'ourwater'
}

FRAGMENT_VERBS = {
    'implement', 'achieve', 'seek', 'work', 'provide', 'ensure', 'reduce',
    'support', 'continue', 'maintain', 'identify', 'include', 'reporting'
}

HIERARCHY_KEYWORDS = {"subsidiary", "partner", "division", "segment", "joint venture", "group"}

def clean_graph(output_dir: str, main_company: str = "Boeing"):
    output_path = Path(output_dir)
    nodes_path = output_path / "nodes.csv"
    edges_path = output_path / "edges.csv"

    if not nodes_path.exists() or not edges_path.exists():
        print(f"Files not found in {output_dir}")
        return

    print(f"Cleaning graph in {output_dir}...")
    nodes_df = pd.read_csv(nodes_path)
    edges_df = pd.read_csv(edges_path)

    # 1. Filter noisy nodes
    def is_noisy(row):
        text = str(row['text']).lower().strip()
        label = row['label']
        
        if text in STOP_WORDS or len(text) <= 2:
            return True
        
        words = text.split()
        if words and words[0] in FRAGMENT_VERBS:
            return True
        
        if label == "Company" and text in {"propane", "fuel oil #2", "jet kerosene", "liquefied petroleum gas"}:
            return False # We will reclassify this, not delete
            
        return False

    nodes_to_drop = nodes_df[nodes_df.apply(is_noisy, axis=1)]['id'].tolist()
    nodes_df = nodes_df[~nodes_df['id'].isin(nodes_to_drop)]
    
    # 2. Reclassify substances
    substances = {"propane", "fuel oil #2", "jet kerosene", "liquefied petroleum gas", "reclaimed on-site", "third-party reclaimed"}
    nodes_df.loc[(nodes_df['label'] == "Company") & (nodes_df['text'].str.lower().isin(substances)), 'label'] = "Metric Context"

    # 3. Clean Edges
    # Remove edges connected to dropped nodes
    edges_df = edges_df[~edges_df['source'].isin(nodes_to_drop)]
    edges_df = edges_df[~edges_df['target'].isin(nodes_to_drop)]

    # 4. Strict Subsidiary Logic
    def validate_subsidiary(row):
        if row['relation'] != "SUBSIDIARY_OF":
            return True
        
        source_id = row['source']
        target_id = row['target']
        
        # Only allow if target is main company
        target_text = str(nodes_df[nodes_df['id'] == target_id]['text'].values[0]).lower() if not nodes_df[nodes_df['id'] == target_id].empty else ""
        if main_company.lower() not in target_text:
            return False
            
        # Check context of source node
        source_node = nodes_df[nodes_df['id'] == source_id]
        if source_node.empty: return False
        
        context = str(source_node['context'].values[0]).lower()
        if any(kw in context for kw in HIERARCHY_KEYWORDS):
            return True
            
        # Reclassify as INTERNAL_TO instead of SUBSIDIARY_OF if it looks like an internal group
        return False

    # Mark edges for removal or update
    subsidiary_edges = edges_df[edges_df['relation'] == "SUBSIDIARY_OF"]
    valid_mask = subsidiary_edges.apply(validate_subsidiary, axis=1)
    
    # Instead of deleting, we change relation to PART_OF for non-explicit ones
    edges_df.loc[(edges_df['relation'] == "SUBSIDIARY_OF") & (~edges_df.index.isin(subsidiary_edges[valid_mask].index)), 'relation'] = "PART_OF"

    # 5. Deduplicate Boeing aliases
    aliases = {"the company", "the group", "our operations", "the boeing company", "boeing"}
    main_id = None
    for alias in aliases:
        match = nodes_df[nodes_df['text'].str.lower() == alias]
        if not match.empty:
            if main_id is None:
                main_id = match.iloc[0]['id']
                nodes_df.loc[nodes_df['id'] == main_id, 'text'] = main_company
            else:
                duplicate_id = match.iloc[0]['id']
                # Remap edges
                edges_df.replace({'source': {duplicate_id: main_id}, 'target': {duplicate_id: main_id}}, inplace=True)
                nodes_df = nodes_df[nodes_df['id'] != duplicate_id]

    # Save cleaned files
    nodes_df.to_csv(nodes_path, index=False)
    edges_df.to_csv(edges_path, index=False)
    print(f"Successfully cleaned graph. New node count: {len(nodes_df)}, Edge count: {len(edges_df)}")

if __name__ == "__main__":
    import sys
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "output/2025-boeing-sustainability-report-1"
    clean_graph(target_dir)
