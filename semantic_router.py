import numpy as np

# Examples of saving facts/expenses
SAVE_SAMPLES = [
    "I bought lunch for 15 dollars today.",
    "My dog's name is Buster.",
    "Sarah is allergic to peanuts.",
    "I spent $50 on an uber.",
    "Just paid rent: $1200.",
    "Remember that my favorite color is blue.",
    "I got a coffee for $4."
]

# Examples of asking questions
QUERY_SAMPLES = [
    "How much did I spend on food this week?",
    "What is my dog's name?",
    "What is Sarah allergic to?",
    "How much is my rent?",
    "Can you tell me what my favorite color is?",
    "What was the total I spent on ubers?",
    "Did I buy coffee today?"
]

class SemanticRouter:
    def __init__(self, embeddings_model):
        self.embeddings = embeddings_model
        
        # Pre-compute embeddings for routing
        self.save_vectors = self.embeddings.embed_documents(SAVE_SAMPLES)
        self.query_vectors = self.embeddings.embed_documents(QUERY_SAMPLES)
        
    def _cosine_similarity(self, v1, v2):
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)
        
    def route_intent(self, text: str) -> str:
        """
        Embeds the incoming text and mathematically checks if it is 
        closer to the SAVE examples or the QUERY examples.
        Returns "SAVE" or "QUERY" in milliseconds.
        """
        input_vector = self.embeddings.embed_query(text)
        
        # Calculate max similarity to SAVE samples
        max_save_sim = max([self._cosine_similarity(input_vector, sv) for sv in self.save_vectors])
        
        # Calculate max similarity to QUERY samples
        max_query_sim = max([self._cosine_similarity(input_vector, qv) for qv in self.query_vectors])
        
        # If neither is a strong match, default to a conversational query
        if max(max_save_sim, max_query_sim) < 0.25:
            return "QUERY"
        
        if max_save_sim > max_query_sim:
            return "SAVE"
        else:
            return "QUERY"
