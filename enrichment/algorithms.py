import logging
import networkx as nx

def run_graph_algorithms(graph):
    """Run graph algorithms such as centrality and connectivity scoring."""
    logging.info("Running graph algorithms")
    
    if len(graph) > 0:
        try:
            # Calculate PageRank for nodes
            pagerank = nx.pagerank(graph)
            for node_id, score in pagerank.items():
                graph.nodes[node_id]["centrality"] = score
        except Exception as e:
            logging.error("Failed to run PageRank: %s", e)
            
    return graph
