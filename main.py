"""
Kai — Personal AI Assistant
FastAPI webhook server with LangChain Agentic RAG (OpenAI + ChromaDB In-Memory)
"""

import os
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from dotenv import load_dotenv

# Load the secrets FIRST
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("kai")

# ── Config ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
WEBHOOK_SECRET   = os.getenv("WEBHOOK_SECRET")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBED_MODEL      = os.getenv("EMBED_MODEL", "text-embedding-3-small")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"
PROFILE_FILE = DATA_DIR / "profile.json"

# Initialize profile if not exists
if not PROFILE_FILE.exists():
    with open(PROFILE_FILE, "w") as f:
        json.dump({"name": "User", "instructions": "I prefer concise and direct answers."}, f)

# Initialize memory file if not exists
if not MEMORY_FILE.exists():
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Kai — Personal AI Assistant",
    description="Secure webhook with Agentic RAG and Web UI",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security ──────────────────────────────────────────────────────────────────
bearer_scheme = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials.credentials != WEBHOOK_SECRET:
        log.warning("Rejected request — invalid Bearer token.")
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token.")
    return credentials.credentials

# ── LLM & Embeddings ──────────────────────────────────────────────────────────
log.info("Initialising OpenAI LLM and embeddings …")

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    openai_api_key=OPENAI_API_KEY,
    temperature=0.2,
)

embeddings = OpenAIEmbeddings(
    model=EMBED_MODEL,
    openai_api_key=OPENAI_API_KEY,
)

# ── Memory Management (In-Memory Chroma + JSON Sync) ──────────────────────────
log.info("Loading memory from JSON...")

vectorstore = Chroma(embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 6})

def load_memory_from_disk():
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory_to_disk(memories):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memories, f, indent=2)

def sync_memory_to_chroma():
    memories = load_memory_from_disk()
    if not memories:
        return
    
    docs = []
    ids = []
    for m in memories:
        docs.append(Document(page_content=m["fact"], metadata={
            "id": m["id"], "source": m["source"], "original": m["original"], "timestamp": m["timestamp"]
        }))
        ids.append(m["id"])
    
    vectorstore.add_documents(docs, ids=ids)
    log.info(f"Loaded {len(docs)} memories into ChromaDB")

sync_memory_to_chroma()

def save_to_memory(fact: str, source: str, original: str) -> str:
    doc_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    # 1. Add to Chroma
    doc = Document(
        page_content=fact,
        metadata={"id": doc_id, "source": source, "original": original, "timestamp": timestamp},
    )
    vectorstore.add_documents([doc], ids=[doc_id])
    
    # 2. Append to JSON
    memories = load_memory_from_disk()
    memories.append({
        "id": doc_id,
        "fact": fact,
        "source": source,
        "original": original,
        "timestamp": timestamp
    })
    save_memory_to_disk(memories)
    
    log.info(f"Saved to ChromaDB and JSON [id={doc_id}]: {fact}")
    return doc_id

def delete_from_memory(doc_id: str):
    # 1. Remove from JSON
    memories = load_memory_from_disk()
    memories = [m for m in memories if m["id"] != doc_id]
    save_memory_to_disk(memories)
    
    # 2. Remove from Chroma
    try:
        vectorstore.delete([doc_id])
    except Exception as e:
        log.warning(f"Error deleting from Chroma: {e}")

# ── Prompts ───────────────────────────────────────────────────────────────────

ROUTER_PROMPT = PromptTemplate.from_template(
    """You are Kai, a personal AI assistant. Classify the following user message.
Reply with exactly one word — either SAVE or QUERY.

- SAVE: The message states a new fact, event, purchase, health log, expense, or any personal information that should be remembered.
- QUERY: The message is a question or request for information, calculation, or recall.

Message: {text}

Classification:"""
)

EXTRACTION_PROMPT = PromptTemplate.from_template(
    """You are Kai. Extract and rewrite the following user statement as a clean, complete factual sentence suitable for long-term memory storage. 
Preserve all numbers, units, dates, and entity names exactly.
Today's date: {today}

User statement: {text}

Clean factual sentence:"""
)

RAG_PROMPT = PromptTemplate.from_template(
    """You are Kai, a personal AI assistant. Use the retrieved memory context below to answer the user's question.
- Perform any required arithmetic accurately.
- If the context is insufficient, say so honestly.
- Be concise and conversational.
Today's date: {today}

--- User Profile & Instructions ---
{profile}

--- Memory Context ---
{context}
--- End of Context ---

User question: {question}

Kai's answer:"""
)

# ── Chain Builders ────────────────────────────────────────────────────────────

def build_router_chain():
    return ROUTER_PROMPT | llm | StrOutputParser()

def build_extraction_chain():
    return EXTRACTION_PROMPT | llm | StrOutputParser()

def build_rag_chain():
    def format_docs(docs):
        return "\n\n".join(
            f"[Memory {i+1}]: {d.page_content}" for i, d in enumerate(docs)
        )

    def load_profile(_):
        with open(PROFILE_FILE, "r") as f:
            p = json.load(f)
        return f"User Name: {p.get('name', 'User')}\nInstructions: {p.get('instructions', '')}"

    return (
        {
            "context":  retriever | format_docs,
            "question": RunnablePassthrough(),
            "today":    lambda _: datetime.now().strftime("%A, %d %B %Y"),
            "profile":  load_profile,
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )

router_chain     = build_router_chain()
extraction_chain = build_extraction_chain()
rag_chain        = build_rag_chain()

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    text: str
    source: Optional[str] = "api"

class WebhookResponse(BaseModel):
    action: str
    message: str
    stored_fact: Optional[str] = None
    doc_id: Optional[str] = None
    error: Optional[str] = None

class ProfilePayload(BaseModel):
    name: str
    instructions: str

# ── Webhook Endpoint (With Crash Protection) ──────────────────────────────────

@app.post("/webhook", response_model=WebhookResponse)
async def webhook(
    payload: WebhookPayload,
    token: str = Depends(verify_token),
):
    try:
        text   = payload.text.strip()
        source = payload.source or "api"
        today  = datetime.now().strftime("%A, %d %B %Y")

        log.info(f"Received payload | source={source} | text={text!r}")

        if not text:
            return JSONResponse(status_code=400, content={"error": "'text' field must not be empty.", "action": "error", "message": "Empty text"})

        # Step 1: Route
        route = router_chain.invoke({"text": text}).strip().upper()
        log.info(f"Router decision: {route}")

        # Step 2a: SAVE
        if "SAVE" in route:
            clean_fact = extraction_chain.invoke({"text": text, "today": today}).strip()
            doc_id     = save_to_memory(clean_fact, source, text)
            return WebhookResponse(
                action="saved",
                message=f"Got it! I've saved that to memory: \"{clean_fact}\"",
                stored_fact=clean_fact,
                doc_id=doc_id,
            )

        # Step 2b: QUERY
        answer = rag_chain.invoke(text)
        log.info(f"RAG answer: {answer}")
        return WebhookResponse(
            action="answered",
            message=answer,
        )
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        # Always return a JSON response to prevent Shortcuts dictionary parsing error!
        return JSONResponse(status_code=500, content={
            "action": "error",
            "message": f"An internal error occurred: {str(e)}",
            "error": str(e)
        })

# ── Web UI Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile(token: str = Depends(verify_token)):
    with open(PROFILE_FILE, "r") as f:
        return json.load(f)

@app.post("/api/profile")
async def update_profile(profile: ProfilePayload, token: str = Depends(verify_token)):
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile.model_dump(), f, indent=2)
    return {"status": "success"}

@app.get("/api/memories")
async def get_memories(token: str = Depends(verify_token)):
    memories = load_memory_from_disk()
    # Return newest first
    return sorted(memories, key=lambda x: x.get("timestamp", ""), reverse=True)

@app.delete("/api/memories/{doc_id}")
async def delete_memory_api(doc_id: str, token: str = Depends(verify_token)):
    delete_from_memory(doc_id)
    return {"status": "success"}

# Serve static files for the UI
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index_file = static_dir / "index.html"
    if index_file.exists():
        with open(index_file, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Kai Web UI</h1><p>static/index.html not found.</p>")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "assistant": "Kai",
        "llm": OPENAI_MODEL,
        "memory_docs": len(load_memory_from_disk()),
        "timestamp": datetime.utcnow().isoformat(),
    }
