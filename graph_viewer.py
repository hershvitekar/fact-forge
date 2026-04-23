import networkx as nx
import os
import sys
import json
from pyvis.network import Network

def view_graph(file_path=None):
    if file_path is None:
        import glob
        import os
        
        # Search for any graph.graphml in output directory or its subdirectories
        search_paths = ["output/**/graph.graphml", "nlp-pipeline/output/**/graph.graphml"]
        found_files = []
        for path in search_paths:
            found_files.extend(glob.glob(path, recursive=True))
            
        if not found_files:
            print("Error: No graph file found in output/ or nlp-pipeline/output/ subdirectories.")
            return
            
        # Get the most recently modified graph file
        file_path = max(found_files, key=os.path.getmtime)
        print(f"Auto-detected most recent graph: {file_path}")

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
        context_str = data.get('context', 'No context available')
        title = f"Entity: {label} | Type: {etype}"
        net.add_node(node_id, label=label, title=title, color=color, size=size, context=context_str, etype=etype, score=data.get('score', 0), centrality=float(centrality))

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
        <div id="search-container" style="position:fixed; top:20px; left:20px; z-index:1000; background:rgba(30,41,59,0.9); padding:15px; border-radius:10px; border:1px solid #334155; color:white; font-family:sans-serif; backdrop-filter: blur(8px); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);">
            <h3 style="margin:0 0 10px 0; color:#60a5fa;">ESG Search</h3>
            <input type="text" id="nodeSearch" placeholder="Type to search..." style="width:200px; padding:8px; border-radius:5px; border:1px solid #475569; background:#0f172a; color:white;">
            <div style="margin-top:12px; padding-top:12px; border-top:1px solid #334155;">
                <label style="color:#94a3b8; font-size:12px;">Top ESG Nodes:</label>
                <div style="display:flex; margin-top:4px;">
                    <input type="number" id="topNInput" placeholder="N (e.g. 10)" style="width:70px; padding:6px; border-radius:5px; border:1px solid #475569; background:#0f172a; color:white;">
                    <button id="applyTopN" style="margin-left:8px; padding:6px 12px; background:#3b82f6; color:white; border:none; border-radius:5px; cursor:pointer;">Filter</button>
                    <button id="clearTopN" style="margin-left:8px; padding:6px 12px; background:#475569; color:white; border:none; border-radius:5px; cursor:pointer;">Clear</button>
                </div>
            </div>
            <div style="font-size:12px; color:#94a3b8; margin-top:8px;">Scroll to zoom | Drag to move</div>
        </div>
        
        <div id="info-panel" style="position:fixed; top:20px; right:20px; width:320px; z-index:1000; background:rgba(30,41,59,0.95); padding:20px; border-radius:12px; border:1px solid #475569; color:white; font-family:sans-serif; display:none; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5); backdrop-filter: blur(12px); transition: all 0.3s ease;">
            <h3 id="info-title" style="margin:0 0 12px 0; color:#60a5fa; font-size: 18px; border-bottom: 1px solid #334155; padding-bottom: 10px;">Node Details</h3>
            <div style="margin-bottom: 10px;"><strong style="color:#94a3b8;">Type:</strong> <span id="info-type" style="color:#e2e8f0; font-weight:500;"></span></div>
            <div>
                 <strong style="color:#94a3b8; display:block; margin-bottom:6px;">Context:</strong>
                 <div id="info-context" style="color:#cbd5e1; font-size: 14px; line-height: 1.6; background: rgba(15,23,42,0.6); padding: 12px; border-radius: 8px; border: 1px solid #334155; max-height: 250px; overflow-y: auto;"></div>
            </div>
            <button onclick="document.getElementById('info-panel').style.display='none'; if(typeof network !== 'undefined') network.unselectAll();" style="margin-top: 18px; width: 100%; padding: 10px; background: #3b82f6; color: white; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; transition: background 0.2s;">Close</button>
        </div>

        <script>
            // Wait for network to be initialized
            setTimeout(function() {
                if (typeof network !== 'undefined') {
                    // Search listener
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
                    
                    // Top N Filter
                    document.getElementById('applyTopN').addEventListener('click', function() {
                        var nStr = document.getElementById('topNInput').value;
                        if (!nStr || parseInt(nStr) <= 0) return;
                        var n = parseInt(nStr);
                        var allNodes = network.body.data.nodes.get();
                        
                        var sortedNodes = [...allNodes].sort(function(a, b) {
                            var centA = parseFloat(a.centrality) || 0;
                            var centB = parseFloat(b.centrality) || 0;
                            if (centB !== centA) return centB - centA;
                            var scoreA = parseFloat(a.score) || 0;
                            var scoreB = parseFloat(b.score) || 0;
                            return scoreB - scoreA;
                        });
                        
                        var topNodes = sortedNodes.slice(0, n);
                        var topIds = new Set(topNodes.map(function(n) { return n.id; }));
                        
                        var updates = allNodes.map(function(node) {
                            return {id: node.id, hidden: !topIds.has(node.id)};
                        });
                        network.body.data.nodes.update(updates);
                        network.fit({animation: true});
                    });

                    document.getElementById('clearTopN').addEventListener('click', function() {
                        document.getElementById('topNInput').value = '';
                        var allNodes = network.body.data.nodes.get();
                        var updates = allNodes.map(function(node) {
                            return {id: node.id, hidden: false};
                        });
                        network.body.data.nodes.update(updates);
                        network.fit({animation: true});
                    });
                    
                    // Click listener for side panel
                    network.on('click', function(properties) {
                        var ids = properties.nodes;
                        if (ids.length > 0) {
                            var clickedNode = network.body.data.nodes.get(ids[0]);
                            if (clickedNode) {
                                document.getElementById('info-title').innerText = clickedNode.label || 'Unknown';
                                document.getElementById('info-type').innerText = clickedNode.etype || 'Unknown';
                                document.getElementById('info-context').innerText = clickedNode.context || 'No context available';
                                document.getElementById('info-panel').style.display = 'block';
                            }
                        } else {
                            document.getElementById('info-panel').style.display = 'none';
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
