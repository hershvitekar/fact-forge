import kuzu
import os
import shutil
import argparse
from pathlib import Path
import pandas as pd
# --- CONFIGURATION ---
parser = argparse.ArgumentParser()
parser.add_argument('--report', required=True, help='Name of the report folder (e.g. hul-...)')
args = parser.parse_args()

PROJECT_ROOT = "/home/hershvitekar/fact-forge-server"
DATA_DIR = Path(f"{PROJECT_ROOT}/data/graphs/{args.report}")
DB_PATH = Path(f"{PROJECT_ROOT}/data/kuzudb")

# 1. Fresh Start
if DB_PATH.exists():
    shutil.rmtree(DB_PATH)

db = kuzu.Database(str(DB_PATH))
conn = kuzu.Connection(db)

def ingest():
    print(f"🚀 Starting Dynamic Ingest for: {args.report}")
    
    # --- 2. LOAD NODES ---
    # Only pick up original nodes, ignore legacy '_cleaned' or '_filtered' files
    node_files = [f for f in DATA_DIR.glob("nodes_*.csv") if not f.stem.endswith(('_cleaned', '_filtered'))]
    
    for f in node_files:
        label = f.stem.replace("nodes_", "")
        print(f"   [Node] {label}...")
        
        # Read headers to build dynamic schema
        df_sample = pd.read_csv(f, nrows=0)
        cols = []
        for col in df_sample.columns:
            if col == 'id': continue
            # Map types
            if col == 'value_float':
                cols.append(f"{col} DOUBLE")
            elif col == 'page':
                cols.append(f"{col} INT64")
            else:
                cols.append(f"{col} STRING")
        
        prop_str = f", {', '.join(cols)}" if cols else ""
        try:
            conn.execute(f"CREATE NODE TABLE {label}(id STRING{prop_str}, PRIMARY KEY (id))")
            conn.execute(f'COPY {label} FROM "{str(f)}" (HEADER=TRUE, PARALLEL=FALSE)')
        except Exception as e:
            print(f"      [!] Error loading {label}: {e}")

    # --- 3. LOAD EDGES (Typed) ---
    edge_files = [f for f in DATA_DIR.glob("edges_*.csv") if not f.stem.endswith(('_cleaned', '_filtered'))]
    
    for f in edge_files:
        # Filename format: edges_{Rel}___{Src}___{Dst}.csv
        # We ONLY accept the new triple-underscore format to avoid table name collisions
        if "___" not in f.stem:
            print(f"   [Edge] Skipping Legacy/Invalid: {f.name}")
            continue
            
        parts = f.stem.replace("edges_", "").split("___")
        if len(parts) < 3:
            print(f"   [Edge] Skipping Malformed: {f.name}")
            continue
            
        rel_name  = parts[0]
        src_table = parts[1]
        dst_table = parts[2]
        
        print(f"   [Edge] {rel_name} ({src_table} -> {dst_table})...")
        
        # Read headers for dynamic edge schema
        df_sample = pd.read_csv(f, nrows=0)
        cols = []
        for col in df_sample.columns:
            if col in ['from', 'to']: continue
            if col == 'confidence':
                cols.append(f"{col} DOUBLE")
            else:
                cols.append(f"{col} STRING")
        
        prop_str = f", {', '.join(cols)}" if cols else ""
        
        # Kùzu requires a unique table name. If multiple types share a relation name,
        # we can either use a combined name or Kùzu's multi-type Rel support.
        # For simplicity and clarity, we use the full type_key as the table name.
        table_name = f.stem.replace("edges_", "")
        
        try:
            conn.execute(f"CREATE REL TABLE {table_name}(FROM {src_table} TO {dst_table}{prop_str})")
            conn.execute(f'COPY {table_name} FROM "{str(f)}" (HEADER=TRUE, PARALLEL=FALSE)')
        except Exception as e:
            print(f"      [!] Error loading {table_name}: {e}")

    print("\n✅ Ingest Complete! You can now query your graph in Kùzu.")

if __name__ == "__main__":
    ingest()
