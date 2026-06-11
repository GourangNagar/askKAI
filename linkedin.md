I finally got tired of jumping between half a dozen apps to track my expenses, save random ideas, and search for facts I forgot. 

So, I built my own "Second Brain" to do it for me. 🧠 

Meet askKAI (yes, a play on "ask AI" 😉), a fully private, Agentic AI Assistant built from the ground up to act as a seamless extension of my memory. 

I wanted KAI to be incredibly fast, incredibly cheap, and strictly factual. The biggest problem with AI is hallucination, I needed absolute accuracy for my expenses and personal data. Here’s how I engineered the stack to guarantee zero hallucinations while supporting multiple users:

🛠 The Architecture:
- Backend: Python + FastAPI 
- Semantic Routing: To eliminate LLM latency on simple decisions, I built a mathematical vector-router. Incoming messages are instantly routed based on cosine similarity to known "Save" vs "Query" vector clusters. Routing time dropped from ~1000ms to ~20ms and costs $0.
- AI Brain (GraphRAG): LangChain + OpenAI (`gpt-4o-mini`) + ChromaDB Vector Storage. I didn't just stop at standard RAG. Whenever I save a fact, askKAI extracts relational edges (e.g., `[Apple] --(owns)--> [iPhone]`) into a local Knowledge Graph (`networkx`). By feeding both Graph context AND Vector context to the LLM, the model is strictly grounded in my own factual embeddings. It doesn't guess or hallucinate.
- Deep Sleep Memory Consolidation: I built a graph-compaction pipeline. Instead of flooding the vector DB with thousands of tiny, disjointed facts (like 5 daily expenses), askKAI runs a "Deep Sleep" consolidation. It feeds raw memories to the LLM, deduplicates them, and compresses them into a single dense summary block to drastically save tokens and improve RAG retrieval accuracy.
- Authentication: Custom JWT-based Multi-Tenant auth. Anyone can sign up, and the database automatically isolates user vectors so everyone gets their own secure "vault".
- Infrastructure: Dockerized and deployed entirely serverless on Google Cloud Run. Because it scales to zero, the cloud compute costs are virtually $0.

💡 My favorite feature? The iOS Automation Hack.
Calling the OpenAI API 20 times a day for every little expense adds up. To optimize costs, I built a custom Apple Shortcut integration. Now, when I log an expense on my iPhone, it saves silently to a local text file. At exactly 11:59 PM, an iOS automation wakes up, grabs the file, and sends all my daily expenses to Kai's webhook in *one single API payload*. 

Kai's AI automatically categorizes everything and commits it to long-term memory for a fraction of a cent. 

If I ever want to know my monthly coffee budget or what my friend is allergic to, I just ask the Web UI, and Kai’s RAG pipeline instantly fetches the exact facts. 

Building a personal AI from scratch was an incredible dive into vector databases, serverless deployments, and LLM orchestration. 

Check out the code here! 👇
🔗 GitLab : https://gitlab.com/gourang1/askkai
🔗 [Insert Live URL or Demo Video]

#Python #AI #OpenAI #FastAPI #CloudRun #LangChain #SoftwareEngineering #Automation #AppleShortcuts