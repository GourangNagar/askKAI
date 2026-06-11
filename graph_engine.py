import json
from pathlib import Path
import sqlite3
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
        
    def _get_db_path(self, user_dir: Path) -> Path:
        return user_dir / "graph.db"
        
    def _init_db(self, user_dir: Path):
        db_path = self._get_db_path(user_dir)
        with sqlite3.connect(db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS edges (
                    source TEXT,
                    target TEXT,
                    relation TEXT,
                    UNIQUE(source, target, relation)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_source ON edges(source)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_target ON edges(target)')

    def wipe_graph(self, user_dir: Path):
        """Completely deletes the graph database to prevent ghost nodes."""
        db_path = self._get_db_path(user_dir)
        if db_path.exists():
            db_path.unlink()

    def extract_and_store_graph(self, text: str, user_dir: Path):
        """Extracts entities and adds them to the user's SQLite graph."""
        self._init_db(user_dir)
        try:
            res = self.extraction_chain.invoke({"text": text}).strip()
            # Clean markdown if present
            if res.startswith("```json"):
                res = res[7:-3]
            tuples = json.loads(res)
            
            with sqlite3.connect(self._get_db_path(user_dir)) as conn:
                for t in tuples:
                    if len(t) == 3:
                        e1, rel, e2 = t
                        # Insert ignore duplicates
                        conn.execute('''
                            INSERT OR IGNORE INTO edges (source, target, relation)
                            VALUES (?, ?, ?)
                        ''', (str(e1).strip(), str(e2).strip(), str(rel).strip()))
        except Exception as e:
            print(f"Graph extraction failed: {e}")

    def query_graph(self, question: str, user_dir: Path) -> str:
        """Extracts entities from the question and returns 1-hop subgraph relationships from SQLite."""
        db_path = self._get_db_path(user_dir)
        if not db_path.exists():
            return "No graph relations found."
            
        try:
            res = self.query_chain.invoke({"text": question}).strip()
            if res.startswith("```json"):
                res = res[7:-3]
            entities = json.loads(res)
            
            graph_context = []
            with sqlite3.connect(db_path) as conn:
                for ent in entities:
                    ent_query = f"%{ent}%"
                    # Get outgoing edges
                    cursor = conn.execute('SELECT source, target, relation FROM edges WHERE source LIKE ?', (ent_query,))
                    for row in cursor:
                        graph_context.append(f"[{row[0]}] --({row[2]})--> [{row[1]}]")
                        
                    # Get incoming edges
                    cursor = conn.execute('SELECT source, target, relation FROM edges WHERE target LIKE ?', (ent_query,))
                    for row in cursor:
                        graph_context.append(f"[{row[0]}] --({row[2]})--> [{row[1]}]")
                        
            # Deduplicate
            graph_context = list(set(graph_context))
            if not graph_context:
                return "No graph relations found."
            return "\n".join(graph_context)
        except Exception as e:
            print(f"Graph query failed: {e}")
            return "No graph relations found."
