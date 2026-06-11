I finally got tired of jumping between half a dozen apps to track my expenses & search for facts I forgot. 
𝗦𝗼 𝗜 𝗯𝘂𝗶𝗹𝘁 𝗺𝘆 𝗼𝘄𝗻 "𝗦𝗲𝗰𝗼𝗻𝗱 𝗕𝗿𝗮𝗶𝗻" 𝘁𝗼 𝗱𝗼 𝗶𝘁 𝗳𝗼𝗿 𝗺𝗲. 🧠 

Meet askKAI (yes, a word play on "ask AI" 😉), a fully private, Agentic AI Assistant built from the ground up to act as a seamless extension of my memory. 

I wanted KAI to be incredibly fast, incredibly cheap, and strictly factual. The biggest problem with AI is hallucination, I needed absolute accuracy for my expenses and personal data. Here’s how I engineered the stack to guarantee zero hallucinations while supporting multiple users:

🛠 𝗧𝗵𝗲 𝗔𝗿𝗰𝗵𝗶𝘁𝗲𝗰𝘁𝘂𝗿𝗲:
- 𝗕𝗮𝗰𝗸𝗲𝗻𝗱: Python + FastAPI 
- 𝗦𝗲𝗺𝗮𝗻𝘁𝗶𝗰 𝗥𝗼𝘂𝘁𝗶𝗻𝗴: To eliminate LLM latency on simple decisions, I built a mathematical vector-router with syntactic heuristics. Incoming messages are instantly routed to "Save", "Query", or "Both" based on cosine similarity and grammar patterns. Routing time dropped from ~1000ms to ~20ms and costs $0.
- 𝗔𝗜 𝗕𝗿𝗮𝗶𝗻 (𝗚𝗿𝗮𝗽𝗵𝗥𝗔𝗚): LangChain + OpenAI (`gpt-4o-mini`) + ChromaDB Vector Storage. I didn't just stop at standard RAG. Whenever I save a fact, askKAI extracts relational edges (e.g., `[Apple] --(owns)--> [iPhone]`) into a lightweight SQLite Knowledge Graph. By feeding both Graph context AND Vector context to the LLM, the model is strictly grounded in my own factual embeddings. It doesn't guess or hallucinate.
- 𝗗𝗲𝗲𝗽 𝗦𝗹𝗲𝗲𝗽 𝗠𝗲𝗺𝗼𝗿𝘆 𝗖𝗼𝗻𝘀𝗼𝗹𝗶𝗱𝗮𝘁𝗶𝗼𝗻: I built a graph-compaction pipeline. Instead of flooding the vector DB with thousands of tiny, disjointed facts (like 5 daily expenses), askKAI runs a "Deep Sleep" consolidation. It feeds raw memories to the LLM, deduplicates them, and compresses them into a single dense summary block to drastically save tokens and improve RAG retrieval accuracy.
- 𝗔𝘂𝘁𝗵𝗲𝗻𝘁𝗶𝗰𝗮𝘁𝗶𝗼𝗻 & 𝗧𝗲𝘀𝘁𝗶𝗻𝗴: Custom JWT-based Multi-Tenant auth isolates user vectors so everyone gets their own secure "vault". The entire system is backed by a robust regression/smoke testing suite to prevent bleeding bugs.
- 𝗜𝗻𝗳𝗿𝗮𝘀𝘁𝗿𝘂𝗰𝘁𝘂𝗿𝗲: Dockerized and deployed entirely serverless on Google Cloud Run. Because it scales to zero, the cloud compute costs are virtually $0.

💡 My favorite feature? The iOS Automation Hack.
Calling the OpenAI API 20 times a day for every little expense adds up. To optimize costs, I compute vectors once and share them between the router and DB, AND I built a custom Apple Shortcut integration. Now, when I log an expense on my iPhone, it saves silently to a local text file. At exactly 11:59 PM, an iOS automation wakes up, grabs the file, and sends all my daily expenses to Kai's webhook in 𝗼𝗻𝗲 𝘀𝗶𝗻𝗴𝗹𝗲 𝗔𝗣𝗜 𝗽𝗮𝘆𝗹𝗼𝗮𝗱. 

Kai's AI automatically categorizes everything and commits it to long-term memory for a fraction of a cent. 

If I ever want to know my monthly coffee budget or what my friend is allergic to, I just ask the Web UI, and Kai’s RAG pipeline instantly fetches the exact facts. 

Building a personal AI from scratch was an incredible dive into vector databases, serverless deployments, and LLM orchestration. 

Check out the code here! 👇
🔗 GitLab : https://gitlab.com/gourang1/askkai
🔗 [Insert Live URL or Demo Video]

#Python #AI #OpenAI #FastAPI #CloudRun #LangChain #SoftwareEngineering #Automation #AppleShortcuts