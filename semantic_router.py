import numpy as np

# Examples of saving facts/expenses
SAVE_SAMPLES = [
    "I bought lunch for 15 dollars today.",
    "My dog's name is Buster.",
    "Sarah is allergic to peanuts.",
    "I spent $50 on an uber.",
    "Just paid rent: $1200.",
    "Remember that my favorite color is blue.",
    "I got a coffee for $4.",
    "My rent is 25000 rupees per month.",
    "My salary is 99k per month.",
    "I owe Ramesh 5000 rupees.",
    "My birthday is on March 15th.",
    "I weigh 72 kg.",
]

# Examples of asking questions
QUERY_SAMPLES = [
    "How much did I spend on food this week?",
    "What is my dog's name?",
    "What is Sarah allergic to?",
    "How much is my rent?",
    "Can you tell me what my favorite color is?",
    "What was the total I spent on ubers?",
    "Did I buy coffee today?",
    "How much money do I have left?",
    "What do I owe Ramesh?",
    "Hello!",
    "Hey, how are you?",
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
        
    def route_intent(self, text: str = None, input_vector: list = None) -> str:
        """
        Embeds the incoming text and mathematically checks if it is 
        closer to the SAVE examples or the QUERY examples.
        Returns "SAVE" or "QUERY" in milliseconds.
        """
        if input_vector is None:
            if not text:
                return "QUERY"
            input_vector = self.embeddings.embed_query(text)
            
        # Calculate max similarity to SAVE samples
        max_save_sim = max([self._cosine_similarity(input_vector, sv) for sv in self.save_vectors])
        
        # Calculate max similarity to QUERY samples
        max_query_sim = max([self._cosine_similarity(input_vector, qv) for qv in self.query_vectors])
        
        # Syntactic heuristic: embeddings capture meaning, not grammar.
        # A question mark strongly suggests QUERY; numbers without '?' suggest SAVE.
        if text:
            has_question = "?" in text
            has_number = any(c.isdigit() for c in text)
            question_words = text.lower().split()[0] in ("how", "what", "when", "where", "who", "why", "did", "is", "can", "do", "does", "which", "hello")
            
            if has_question or question_words:
                max_query_sim += 0.05
            elif has_number and not has_question:
                max_save_sim += 0.05
        
        # If neither is a strong match, default to a conversational query
        if max(max_save_sim, max_query_sim) < 0.25:
            return "QUERY"
        
        # If both scores are high and close together, the message contains both a fact and a question
        if min(max_save_sim, max_query_sim) > 0.28 and abs(max_save_sim - max_query_sim) < 0.08:
            return "BOTH"
        
        if max_save_sim > max_query_sim:
            return "SAVE"
        else:
            return "QUERY"
