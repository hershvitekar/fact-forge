import json
import re
import logging
from pathlib import Path

def process_document_tables(markdown_text, json_tables_path):
    """
    Cleans markdown of tables and injects linearized natural language facts 
    from the high-fidelity JSON tables file.
    """
    if not Path(json_tables_path).exists():
        logging.warning(f"JSON tables file not found at {json_tables_path}. Skipping table processing.")
        return markdown_text

    try:
        with open(json_tables_path, 'r', encoding='utf-8') as f:
            tables_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON tables: {e}")
        return markdown_text

    # 1. Linearize all tables
    linearized_tables = {}
    for table in tables_data:
        idx = table.get("table_index")
        grid = table.get("data", {}).get("data", {}).get("grid", [])
        if not grid:
            continue
            
        facts = linearize_grid(grid)
        linearized_tables[idx] = "\n".join(facts)

    # 2. Clean Markdown and Replace with Linearized Data
    # We look for the standard Markdown table pattern
    # This regex looks for lines starting and ending with | and a separator row |---|
    table_pattern = re.compile(r'(\|.*\|(?:\n\|[-:| ]*\|)(?:\n\|.*\|)+)', re.MULTILINE)
    
    matches = list(table_pattern.finditer(markdown_text))
    
    # We replace from back to front to keep offsets valid
    cleaned_text = markdown_text
    
    # Note: The mapping between MD tables and JSON table_index is 1:1 in sequential order
    # provided by Docling/Parser.
    for i, match in enumerate(reversed(matches)):
        # Calculate the actual index (matches are found in order, but we reversed the list)
        actual_idx = len(matches) - 1 - i
        
        replacement = linearized_tables.get(actual_idx, "")
        if replacement:
            # Wrap in a structural hint for the NLP model
            replacement = f"\n> [Structured Data from Table {actual_idx}]:\n{replacement}\n"
        
        cleaned_text = cleaned_text[:match.start()] + replacement + cleaned_text[match.end():]

    logging.info(f"Processed {len(matches)} tables: replaced markdown blocks with linearized facts.")
    return cleaned_text

def linearize_grid(grid):
    """Converts a table grid into a list of natural language sentences."""
    if not grid:
        return []

    num_rows = len(grid)
    num_cols = len(grid[0])
    
    # Identify headers
    col_headers = []
    # Check if the first row is a header row
    if any(cell.get("column_header") for cell in grid[0]):
        col_headers = [cell.get("text", "").strip() for cell in grid[0]]
    
    facts = []
    
    # If it's a simple 2-column key-value table without complex headers
    if num_cols == 2 and not col_headers:
        for row in grid:
            key = row[0].get("text", "").strip()
            val = row[1].get("text", "").strip()
            if key and val:
                facts.append(f"{key} is {val}.")
        return facts

    # General grid linearization
    for r_idx, row in enumerate(grid):
        # Skip header row if we captured it
        if col_headers and r_idx == 0:
            continue
            
        row_header = ""
        row_data = []
        
        for c_idx, cell in enumerate(row):
            text = cell.get("text", "").strip()
            if not text:
                continue
                
            if cell.get("row_header") or (c_idx == 0 and not col_headers):
                row_header = text
            else:
                col_name = col_headers[c_idx] if c_idx < len(col_headers) else f"Column {c_idx}"
                if row_header:
                    facts.append(f"For {row_header}, the {col_name} is {text}.")
                else:
                    facts.append(f"The {col_name} is {text}.")
                    
    return facts

if __name__ == "__main__":
    # Quick syntax check
    test_text = "| A | B |\n|---|---|\n| 1 | 2 |"
    print("Syntax check passed.")
