import networkx as nx
import os
import sys
import json
from pyvis.network import Network

def view_graph(file_path=None):
    if file_path is None:
        # Check relative to new location (inside nlp-pipeline)
        if os.path.exists("output/graph.graphml"):
            file_path = "output/graph.graphml"
        # Fallback for root execution
        elif os.path.exists("nlp-pipeline/output/graph.graphml"):
            file_path = "nlp-pipeline/output/graph.graphml"
        else:
            print("Error: No graph file found in output/ or nlp-pipeline/output/")
            return

    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    print(f"Loading graph from {file_path}...")
    
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.graphml':
            G = nx.read_graphml(file_path)
        elif ext == '.gexf':
            G = nx.read_gexf(file_path)
        else:
            print(f"Unsupported format: {ext}")
            return
    except Exception as e:
        print(f"Error loading graph: {e}")
        return

    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()
    print(f"Graph loaded: {num_nodes} nodes, {num_edges} edges.")

    # Create Pyvis network
    net = Network(height="850px", width="100%", bgcolor="#0f172a", font_color="white", directed=True)
    
    # Configure physics for stability
    net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=100, spring_strength=0.08)

    # Professional Color Map
    color_map = {
        'emission type': '#f87171', 'sustainability initiative': '#4ade80',
        'stakeholder group': '#60a5fa', 'environmental risk': '#fb923c',
        'ESG framework or standard': '#a78bfa', 'ESG metric': '#fbbf24',
        'Standard': '#a78bfa', 'Requirement': '#f87171', 'Concept': '#60a5fa'
    }

    # Add Nodes
    for node_id, data in G.nodes(data=True):
        label = data.get('text') or data.get('label') or str(node_id)
        etype = data.get('label') or data.get('atype') or 'Unknown'
        color = color_map.get(etype, '#94a3b8')
        
        centrality = data.get('centrality', 0)
        size = 20 + (float(centrality) * 200) if centrality else 25
        
        # Tooltip
        title = f"Entity: {label} | Type: {etype}"
        net.add_node(node_id, label=label, title=title, color=color, size=size)

    # Add Edges
    for source, target, data in G.edges(data=True):
        relation = data.get('relation') or data.get('etype') or ''
        net.add_edge(source, target, label=relation, color='#475569', arrows='to')

    # Add some basic options directly
    net.options.edges.smooth.enabled = True
    net.options.interaction.hover = True
    net.options.interaction.navigationButtons = True
    
    # Enable the configuration UI
    net.show_buttons(filter_=['physics', 'nodes', 'edges', 'interaction'])

    output_html = "graph_explorer.html"
    print(f"Saving explorer to {output_html}...")
    net.save_graph(output_html)
    
    # Manual injection of search bar
    try:
        with open(output_html, 'r') as f:
            html = f.read()
        
        search_html = """
        <div id="search-container" style="position:fixed; top:20px; left:20px; z-index:1000; background:rgba(30,41,59,0.9); padding:15px; border-radius:10px; border:1px solid #334155; color:white; font-family:sans-serif;">
            <h3 style="margin:0 0 10px 0; color:#60a5fa;">ESG Search</h3>
            <input type="text" id="nodeSearch" placeholder="Type to search..." style="width:200px; padding:8px; border-radius:5px; border:1px solid #475569; background:#0f172a; color:white;">
            <div style="font-size:12px; color:#94a3b8; margin-top:8px;">Scroll to zoom | Drag to move</div>
        </div>
        <script>
            // Wait for network to be initialized
            setTimeout(function() {
                if (typeof network !== 'undefined') {
                    document.getElementById('nodeSearch').addEventListener('input', function(e) {
                        var term = e.target.value.toLowerCase();
                        if(!term) return;
                        var matches = network.body.data.nodes.get({
                            filter: function (item) {
                                return item.label && item.label.toLowerCase().includes(term);
                            }
                        });
                        if (matches.length > 0) {
                            network.focus(matches[0].id, {scale: 1, animation: true});
                            network.selectNodes([matches[0].id]);
                        }
                    });
                }
            }, 1000);
        </script>
        """
        html = html.replace('</body>', search_html + '</body>')
        
        with open(output_html, 'w') as f:
            f.write(html)
    except Exception as e:
        print(f"Note: Could not inject search bar: {e}")

    print(f"Done! Opening {output_html}...")
    import webbrowser
    webbrowser.open('file://' + os.path.realpath(output_html))

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    view_graph(path)
