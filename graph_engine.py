import json
from pathlib import Path
import networkx as nx
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

GRAPH_EXTRACTION_PROMPT = PromptTemplate.from_template(
    """You are an advanced Knowledge Graph Extractor.
Extract all relationships from the user's statement into exactly a JSON list of (Entity1, Relationship, Entity2) tuples.
Example 1: "Sarah is allergic to peanuts." -> [["Sarah", "allergic_to", "peanuts"]]
Example 2: "I spent $15 on lunch at Subway." -> [["User", "spent", "$15"], ["User", "bought", "lunch"], ["lunch", "location", "Subway"]]
Output ONLY valid JSON. No markdown, no conversational text.

User statement: {text}
Output JSON:"""
)

GRAPH_QUERY_PROMPT = PromptTemplate.from_template(
    """You are a Graph Entity Extractor.
Extract the core entities from this question as a JSON list of strings.
Example 1: "What is Sarah allergic to?" -> ["Sarah"]
Example 2: "How much did I spend at Subway?" -> ["Subway", "User"]
Output ONLY valid JSON. No markdown.

Question: {text}
Output JSON:"""
)

class GraphEngine:
    def __init__(self, llm):
        self.llm = llm
        self.extraction_chain = GRAPH_EXTRACTION_PROMPT | llm | StrOutputParser()
        self.query_chain = GRAPH_QUERY_PROMPT | llm | StrOutputParser()
        
    def _get_graph_file(self, user_dir: Path) -> Path:
        return user_dir / "graph.json"
        
    def _load_graph(self, user_dir: Path) -> nx.DiGraph:
        g_file = self._get_graph_file(user_dir)
        if g_file.exists():
            try:
                with open(g_file, "r") as f:
                    data = json.load(f)
                return nx.node_link_graph(data)
            except Exception:
                return nx.DiGraph()
        return nx.DiGraph()
        
    def _save_graph(self, g: nx.DiGraph, user_dir: Path):
        g_file = self._get_graph_file(user_dir)
        with open(g_file, "w") as f:
            json.dump(nx.node_link_data(g), f, indent=2)

    def extract_and_store_graph(self, text: str, user_dir: Path):
        """Extracts entities and adds them to the user's NetworkX graph."""
        try:
            res = self.extraction_chain.invoke({"text": text}).strip()
            # Clean markdown if present
            if res.startswith("```json"):
                res = res[7:-3]
            tuples = json.loads(res)
            
            g = self._load_graph(user_dir)
            for t in tuples:
                if len(t) == 3:
                    e1, rel, e2 = t
                    # Add nodes and edge
                    g.add_node(e1)
                    g.add_node(e2)
                    g.add_edge(e1, e2, relation=rel)
            self._save_graph(g, user_dir)
        except Exception as e:
            print(f"Graph extraction failed: {e}")

    def query_graph(self, question: str, user_dir: Path) -> str:
        """Extracts entities from the question and returns 1-hop subgraph relationships."""
        try:
            res = self.query_chain.invoke({"text": question}).strip()
            if res.startswith("```json"):
                res = res[7:-3]
            entities = json.loads(res)
            
            g = self._load_graph(user_dir)
            graph_context = []
            
            for ent in entities:
                # Find exact or partial matches
                matched_nodes = [n for n in g.nodes() if str(ent).lower() in str(n).lower()]
                for node in matched_nodes:
                    # Get outgoing edges
                    for neighbor in g.successors(node):
                        rel = g.edges[node, neighbor].get("relation", "related_to")
                        graph_context.append(f"[{node}] --({rel})--> [{neighbor}]")
                    # Get incoming edges
                    for neighbor in g.predecessors(node):
                        rel = g.edges[neighbor, node].get("relation", "related_to")
                        graph_context.append(f"[{neighbor}] --({rel})--> [{node}]")
                        
            # Deduplicate
            graph_context = list(set(graph_context))
            if not graph_context:
                return "No graph relations found."
            return "\n".join(graph_context)
        except Exception as e:
            print(f"Graph query failed: {e}")
            return "No graph relations found."
