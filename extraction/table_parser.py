import re
import logging

def find_markdown_tables(text: str):
    if not text: return []
    pattern = r'((?:\|.*\|(?:\n|$))+)'
    potential_tables = re.findall(pattern, text, re.MULTILINE)
    valid_tables = []
    for table_str in potential_tables:
        if '|' in table_str and '-' in table_str:
            valid_tables.append(table_str.strip())
    return valid_tables

def parse_markdown_table(table_str: str):
    if not table_str: return []
    lines = table_str.strip().split('\n')
    if len(lines) < 2: return []
    parsed_rows = []
    for line in lines:
        if re.match(r'^\|[\s\-\:\|]+\|$', line): continue
        cells = [c.strip() for c in line.split('|')]
        if cells and not cells[0]: cells = cells[1:]
        if cells and not cells[-1]: cells = cells[:-1]
        if cells: parsed_rows.append(cells)
    return parsed_rows

def get_tables_with_context(text: str):
    if not text or not isinstance(text, str): return []
    lines = text.split('\n')
    tables = []
    current_heading = "Top Level"
    current_page = 1
    current_table_lines = []
    
    for line in lines:
        # Detect page markers
        page_match = re.search(r'<!-- PAGE_BREAK: (\d+) -->', line)
        if page_match:
            current_page = int(page_match.group(1))
            continue
            
        if line.startswith('#'): 
            current_heading = line.strip('# ').strip()
        if line.strip().startswith('|'): 
            current_table_lines.append(line)
        else:
            if current_table_lines:
                table_str = '\n'.join(current_table_lines)
                if '-' in table_str:
                    rows = parse_markdown_table(table_str)
                    if rows: 
                        tables.append({
                            "heading": current_heading, 
                            "rows": rows,
                            "page": current_page
                        })
                current_table_lines = []
    
    # Handle the last table if the file doesn't end with a newline
    if current_table_lines:
        table_str = '\n'.join(current_table_lines)
        if '-' in table_str:
            rows = parse_markdown_table(table_str)
            if rows: 
                tables.append({
                    "heading": current_heading, 
                    "rows": rows,
                    "page": current_page
                })
    return tables

def extract_esg_facts_from_tables(tables):
    facts = []
    if not tables: return facts

    for table in tables:
        heading = table.get("heading", "Unknown")
        rows = table.get("rows", [])
        page = table.get("page", 1)
        if len(rows) < 2: continue
            
        header = rows[0]
        # 1. Identify year columns and potential unit columns
        year_cols = {} # index -> year string
        unit_col_idx = -1
        
        for i, cell in enumerate(header):
            c_lower = cell.lower()
            if "2024-25" in cell: year_cols[i] = "2025"
            elif "2023-24" in cell: year_cols[i] = "2024"
            
            if any(x in c_lower for x in ["unit", "parameter", "uom"]):
                unit_col_idx = i
        
        # 2. Check for a sub-header row (e.g. Male | Female | Total)
        sub_headers = {} # index -> sub-header string
        data_start_idx = 1
        if len(rows) > 2:
            second_row = rows[1]
            if any(x in " ".join(second_row).lower() for x in ["male", "female", "total", "direct", "indirect"]):
                sub_headers = {i: cell for i, cell in enumerate(second_row) if cell}
                data_start_idx = 2

        # 3. Process data rows
        for row in rows[data_start_idx:]:
            if not row: continue
            base_metric = row[0]
            
            # Get unit from the dedicated unit column if it exists
            row_unit = ""
            if unit_col_idx != -1 and unit_col_idx < len(row):
                row_unit = row[unit_col_idx]

            for col_idx, year in year_cols.items():
                if col_idx < len(row):
                    raw_val = row[col_idx]
                    if raw_val and raw_val not in ("-", "None", ""):
                        # Header Merging: Append sub-header if available
                        qualifier = sub_headers.get(col_idx, "")
                        full_metric = f"{base_metric} ({qualifier})" if qualifier else base_metric
                        
                        # CONTEXT-AWARE NAMING: Prepend heading if metric is generic (Task 12)
                        GENERIC_NAMES = {"total", "male", "female", "category", "parameter", "value", "metric"}
                        is_generic = base_metric.lower().strip() in GENERIC_NAMES
                        if is_generic and heading and heading != "Unknown":
                            full_metric = f"{heading} - {full_metric}"
                        
                        # Data Cleaning
                        clean_val = raw_val.replace(",", "").replace("%", "").strip()
                        if "Net:" in clean_val:
                            clean_val = clean_val.split("Net:")[-1].split()[0].strip("*")
                        
                        facts.append({
                            "metric": full_metric,
                            "value": clean_val,
                            "unit": row_unit or ("%" if "%" in raw_val else ""),
                            "year": year,
                            "heading": heading,
                            "raw_source": raw_val,
                            "context": f"Table Row: {' | '.join([str(c) for c in row])}",
                            "page": page
                        })
    return facts
