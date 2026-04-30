import streamlit as st
import kuzu
import pandas as pd
from pathlib import Path

# --- PAGE CONFIG ---
st.set_page_config(page_title="FactForge Cypher Explorer", page_icon="🧬", layout="wide")

# --- APP STYLE ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stDataFrame { border: 1px solid #30363d; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🧬 FactForge: Kùzu Cypher Explorer")
st.markdown("Query your ESG Knowledge Graph using Cypher directly over the NAS.")

# --- SIDEBAR CONFIG ---
st.sidebar.header("🛠️ Configuration")
db_path = st.sidebar.text_input("Database Path (NAS)", value="Z:/fact-forge-server/data/kuzudb")

@st.cache_resource
def get_connection(path):
    try:
        db = kuzu.Database(path)
        return kuzu.Connection(db)
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        return None

conn = get_connection(db_path)

# --- QUICK QUERIES ---
st.sidebar.subheader("🚀 Quick Templates")
templates = {
    "Pillar Summary": "MATCH (p:ESG_Pillar) RETURN p.id, p.text",
    "KPI Trend Analysis": """MATCH (m:ESG_Metric)-[rel]->(v:Quantitative_Value)-[r]->(y:Reporting_Year)
WHERE label(rel) CONTAINS 'MEASURES' AND label(r) CONTAINS 'reported_at'
RETURN m.id, v.text, y.id
ORDER BY m.id, y.id""",
    "Safety (LTIFR) Regression": """MATCH (m:ESG_Metric)-[rel]->(v:Quantitative_Value)-[r]->(y:Reporting_Year)
WHERE m.id CONTAINS 'ltifr' AND label(rel) CONTAINS 'MEASURES'
RETURN y.id, v.text""",
    "List All Companies": "MATCH (c:Company) RETURN c.id, c.text",
    "Relationship Types": "CALL SHOW_TABLES() RETURN *"
}

selected_template = st.sidebar.selectbox("Choose a template", list(templates.keys()))
query_input = st.text_area("Cypher Query", value=templates[selected_template], height=200)

if st.button("▶️ Run Query"):
    if conn:
        try:
            with st.spinner("Executing..."):
                result = conn.execute(query_input)
                
                # Fetch all results into a list
                rows = []
                while result.has_next():
                    rows.append(result.get_next())
                
                if rows:
                    # Get column names from the result object
                    # Kuzu query result column names are available via result.get_column_names()
                    df = pd.DataFrame(rows, columns=result.get_column_names())
                    
                    st.success(f"Fetched {len(rows)} rows.")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Query returned no results.")
        except Exception as e:
            st.error(f"Query Error: {e}")
    else:
        st.warning("Please check your database path in the sidebar.")

# --- FOOTER ---
st.sidebar.markdown("---")
st.sidebar.info("Antigravity ESG Engine v2.6")
