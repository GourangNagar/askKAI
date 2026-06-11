"""
Kai — Personal AI Assistant
FastAPI webhook server with LangChain Agentic RAG, OpenAI, ChromaDB, and Google OAuth Multi-Tenancy.
"""

import os
import uuid


import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))
from typing import Optional, List
import secrets

import jwt
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import bcrypt
from filelock import FileLock

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from graph_engine import GraphEngine

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
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBED_MODEL      = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Multi-tenant Auth config
JWT_SECRET           = os.getenv("JWT_SECRET", "super-secret-default-key-change-me")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

if not USERS_FILE.exists():
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Kai — Personal AI Assistant",
    description="Secure webhook with Multi-Tenant Agentic RAG and Web UI",
    version="3.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security & Auth (Local Email/Password) ──────────────────────────────────

WORDLIST = ["apple", "ocean", "zebra", "moon", "star", "river", "mountain", "cloud", "sun", "tree", "bird", "fish", "bear", "wolf", "fox", "lion", "tiger", "hawk", "eagle", "snake", "lizard", "frog", "toad", "whale", "shark", "dolphin", "turtle", "crab", "lobster", "octopus", "squid", "jellyfish", "coral", "reef", "sand", "shell", "wave", "tide", "surf", "breeze", "wind", "storm", "rain", "snow", "ice", "frost", "fire", "flame", "spark", "ash", "smoke", "coal", "rock", "stone", "pebble", "dust", "dirt", "soil", "mud", "clay", "sand", "glass", "metal", "iron", "steel", "gold", "silver", "copper", "brass", "bronze", "wood", "leaf", "branch", "root", "bark", "seed", "flower", "fruit", "berry", "nut", "cone", "mushroom", "fungus", "moss", "fern", "grass", "weed", "vine", "bush", "shrub", "plant", "herb", "spice", "salt", "pepper", "sugar", "honey"]

class AuthPayload(BaseModel):
    email: str
    password: Optional[str] = None
    name: Optional[str] = None
    recovery_phrase: Optional[str] = None

def load_users():
    lock_file = USERS_FILE.with_suffix('.lock')
    with FileLock(str(lock_file), timeout=5):
        with open(USERS_FILE, "r") as f:
            return json.load(f)

def save_users(users):
    lock_file = USERS_FILE.with_suffix('.lock')
    with FileLock(str(lock_file), timeout=5):
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=2)

@app.post("/auth/register")
async def register(payload: AuthPayload):
    users = load_users()
    email = payload.email.lower().strip()
    
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required.")
        
    if email in users:
        raise HTTPException(status_code=400, detail="Email already registered.")
        
    hashed_password = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    
    # Generate 12-word recovery phrase
    phrase_words = [secrets.choice(WORDLIST) for _ in range(12)]
    recovery_phrase = " ".join(phrase_words)
    hashed_phrase = bcrypt.hashpw(recovery_phrase.encode(), bcrypt.gensalt()).decode()
    
    users[email] = {
        "email": email,
        "password": hashed_password,
        "recovery_phrase": hashed_phrase,
        "created_at": datetime.utcnow().isoformat()
    }
    save_users(users)
    
    # Save the name to profile.json directly
    if payload.name:
        pf = get_profile_file(email)
        # Create user dir if it doesn't exist
        get_user_dir(email)
        lock_file = pf.with_suffix('.lock')
        with FileLock(str(lock_file), timeout=5):
            with open(pf, "w") as f:
                json.dump({"name": payload.name, "instructions": "I prefer concise and direct answers."}, f, indent=2)
    
    # Generate JWT
    jwt_token = jwt.encode({
        "sub": email, 
        "exp": int(datetime.utcnow().timestamp()) + (30 * 24 * 3600)
    }, JWT_SECRET, algorithm="HS256")
    
    return {"token": jwt_token, "recovery_phrase": recovery_phrase}

@app.post("/auth/login")
async def login(payload: AuthPayload):
    users = load_users()
    email = payload.email.lower().strip()
    
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password required.")

    user = users.get(email)
    if not user or not bcrypt.checkpw(payload.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
        
    # Generate JWT
    jwt_token = jwt.encode({
        "sub": email, 
        "exp": datetime.utcnow().timestamp() + (30 * 24 * 3600)
    }, JWT_SECRET, algorithm="HS256")
    
    return {"token": jwt_token}

@app.post("/auth/reset-password")
async def reset_password(payload: AuthPayload):
    users = load_users()
    email = payload.email.lower().strip()
    
    if not email or not payload.recovery_phrase or not payload.password:
        raise HTTPException(status_code=400, detail="Email, recovery phrase, and new password are required.")
        
    user = users.get(email)
    if not user or "recovery_phrase" not in user:
        raise HTTPException(status_code=400, detail="Invalid email or recovery phrase.")
        
    if not bcrypt.checkpw(payload.recovery_phrase.strip().encode(), user["recovery_phrase"].encode()):
        raise HTTPException(status_code=401, detail="Invalid recovery phrase.")
        
    # Update password
    hashed_password = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    users[email]["password"] = hashed_password
    save_users(users)
    
    return {"status": "success", "message": "Password updated successfully."}

bearer_scheme = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["sub"] # Returns the user's email as the user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except Exception as e:
        log.warning(f"Rejected request — invalid JWT token. {e}")
        raise HTTPException(status_code=401, detail="Invalid token.")

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

# ── Data Isolation (Multi-Tenant) ─────────────────────────────────────────────
CHROMA_DIR = DATA_DIR / "chromadb"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

vectorstore = Chroma(
    persist_directory=str(CHROMA_DIR),
    embedding_function=embeddings
)

graph_engine = GraphEngine(llm)

def get_user_dir(user_id: str) -> Path:
    # Use email as folder name (sanitize it for filesystem safety)
    safe_id = "".join(c for c in user_id if c.isalnum() or c in ('@', '.', '-', '_'))
    
    # Path Traversal Protection: if the safe_id contains ".." or is otherwise risky, fallback to hash
    if ".." in safe_id or safe_id.startswith(".") or safe_id.startswith("-"):
        safe_id = hashlib.sha256(user_id.encode()).hexdigest()
        
    user_dir = DATA_DIR / safe_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def get_memory_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "memory.json"

def get_profile_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "profile.json"

def load_profile_from_disk(user_id: str) -> dict:
    pf = get_profile_file(user_id)
    lock_file = pf.with_suffix('.lock')
    if pf.exists():
        with FileLock(str(lock_file), timeout=5):
            with open(pf, "r") as f:
                return json.load(f)
    return {"name": "User", "instructions": "I prefer concise and direct answers."}

def load_memory_from_disk(user_id: str) -> list:
    mf = get_memory_file(user_id)
    lock_file = mf.with_suffix('.lock')
    if mf.exists():
        with FileLock(str(lock_file), timeout=5):
            with open(mf, "r") as f:
                return json.load(f)
    return []

def save_memory_to_disk(memories: list, user_id: str):
    mf = get_memory_file(user_id)
    lock_file = mf.with_suffix('.lock')
    with FileLock(str(lock_file), timeout=5):
        with open(mf, "w") as f:
            json.dump(memories, f, indent=2)

def sync_all_memory_to_chroma():
    log.info("Loading all tenant memories into ChromaDB...")
    docs = []
    ids = []
    
    # Iterate through all user directories in data/
    for user_dir in DATA_DIR.iterdir():
        if user_dir.is_dir() and user_dir.name != "chromadb":
            user_id = user_dir.name
            memories = load_memory_from_disk(user_id)
            for m in memories:
                docs.append(Document(page_content=m["fact"], metadata={
                    "id": m["id"], 
                    "user_id": user_id,
                    "source": m["source"], 
                    "original": m["original"], 
                    "timestamp": m["timestamp"]
                }))
                ids.append(m["id"])
    
    if docs:
        vectorstore.add_documents(docs, ids=ids)
        log.info(f"Loaded {len(docs)} memories across all tenants into ChromaDB")

if vectorstore._collection.count() == 0:
    log.info("ChromaDB is empty! Running initial sync from disk...")
    sync_all_memory_to_chroma()
else:
    log.info(f"ChromaDB loaded from disk. Contains {vectorstore._collection.count()} vectors. Skipping sync.")

def save_to_memory(fact: str, source: str, original: str, user_id: str) -> str:
    doc_id = str(uuid.uuid4())
    timestamp = datetime.now(IST).isoformat()
    
    # 1. Add to Chroma with user_id metadata
    doc = Document(
        page_content=fact,
        metadata={"id": doc_id, "user_id": user_id, "source": source, "original": original, "timestamp": timestamp},
    )
    vectorstore.add_documents([doc], ids=[doc_id])
    
    # 2. Append to JSON
    memories = load_memory_from_disk(user_id)
    memories.append({
        "id": doc_id,
        "fact": fact,
        "source": source,
        "original": original,
        "timestamp": timestamp
    })
    save_memory_to_disk(memories, user_id)
    
    log.info(f"Saved memory for user [{user_id}] | id={doc_id}")
    return doc_id

def delete_from_memory(doc_id: str, user_id: str) -> bool:
    memories = load_memory_from_disk(user_id)
    
    # Ensure this doc belongs to the user
    target_mem = next((m for m in memories if m["id"] == doc_id), None)
    if not target_mem:
        return False
        
    # 1. Remove from JSON
    memories = [m for m in memories if m["id"] != doc_id]
    save_memory_to_disk(memories, user_id)
    
    # 2. Remove from Chroma
    try:
        vectorstore.delete([doc_id])
    except Exception as e:
        log.warning(f"Error deleting from Chroma: {e}")
        
    return True

# ── Prompts ───────────────────────────────────────────────────────────────────

ROUTER_PROMPT = PromptTemplate.from_template(
    """You are an intent classification engine for a personal AI assistant.
Determine if the user's message is a statement of fact to be saved, a question to be answered, or both.

Categories:
- SAVE: The user is stating a fact, preference, or logging an expense. (e.g., "I work at Natwest", "I spent $15 on lunch", "My name is John")
- QUERY: The user is asking a question or requesting information. (e.g., "What is my salary?", "How much did I spend?", "Tell me my job")
- BOTH: The message contains both a new fact to save AND a question. (e.g., "I just got paid $5000, what is my total balance?")

User message: {text}

Output ONLY the exact category name (SAVE, QUERY, or BOTH)."""
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

--- Memory Context (Vectors) ---
{context}

--- Relational Graph Context (Entities) ---
{graph_context}

--- Recent Conversation ---
{history}
--- End of Context ---

Question: {question}
Kai's answer:"""
)

CONSOLIDATION_PROMPT = PromptTemplate.from_template(
    """You are Kai. Your task is to perform "Deep Sleep Memory Consolidation".
You are given a list of disjointed, raw memories logged over time.
Your task is to deduplicate them, aggregate related items (especially expenses), and write a single, dense, factual summary block.
Do NOT lose any unique facts. If there are distinct unrelated facts, combine them logically.
Output ONLY the final consolidated memory block. Do not add conversational filler.

--- Raw Memories ---
{memories}

Consolidated Memory Block:"""
)

# ── Chain Builders ────────────────────────────────────────────────────────────

extraction_chain = EXTRACTION_PROMPT | llm | StrOutputParser()
consolidation_chain = CONSOLIDATION_PROMPT | llm | StrOutputParser()
router_chain = ROUTER_PROMPT | llm | StrOutputParser()

def build_dynamic_rag_chain(user_id: str, query_embedding: list):
    
    def fetch_docs(_):
        # Bypass the standard retriever and use the pre-computed embedding to save 1 API call
        docs = vectorstore.similarity_search_by_vector(query_embedding, k=6, filter={"user_id": user_id})
        return "\n\n".join(f"[Memory {i+1}]: {d.page_content}" for i, d in enumerate(docs))

    def load_profile(_):
        p = load_profile_from_disk(user_id)
        return f"User Name: {p.get('name', 'User')}\nInstructions: {p.get('instructions', '')}"

    return (
        {
            "context":  fetch_docs,
            "graph_context": lambda x: graph_engine.query_graph(x["question"], get_user_dir(user_id)),
            "history":  lambda x: "\n".join(x.get("history", [])) if x.get("history") else "No recent history.",
            "question": lambda x: x["question"],
            "today":    lambda _: datetime.now().strftime("%A, %d %B %Y"),
            "profile":  load_profile,
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    text: str
    source: Optional[str] = "api"
    history: Optional[List[str]] = None

class WebhookResponse(BaseModel):
    action: str
    message: str
    stored_fact: Optional[str] = None
    doc_id: Optional[str] = None
    error: Optional[str] = None

class ProfilePayload(BaseModel):
    name: str
    instructions: str

# ── Webhook Endpoint (Multi-Tenant) ───────────────────────────────────────────

@app.post("/webhook", response_model=WebhookResponse)
async def webhook(
    payload: WebhookPayload,
    user_id: str = Depends(verify_token),
):
    try:
        text   = payload.text.strip()
        source = payload.source or "api"
        today  = datetime.now(IST).strftime("%A, %d %B %Y")
        history = payload.history or []

        log.info(f"Received payload | user={user_id} | source={source} | text={text!r}")

        if not text:
            return JSONResponse(status_code=400, content={"error": "'text' field must not be empty.", "action": "error", "message": "Empty text"})

        # Step 1: Pre-compute Embedding for downstream RAG
        query_embedding = embeddings.embed_query(text)
            
        # Step 2: Route using LLM for highly accurate semantic intent
        route_result = router_chain.invoke({"text": text}).strip().upper()
        
        # Parse result safely
        route = "QUERY"
        if "BOTH" in route_result:
            route = "BOTH"
        elif "SAVE" in route_result:
            route = "SAVE"

        # Step 2a: SAVE
        if route == "SAVE":
            clean_fact = extraction_chain.invoke({"text": text, "today": today}).strip()
            doc_id     = save_to_memory(clean_fact, source, text, user_id)
            
            # Extract and update Knowledge Graph
            graph_engine.extract_and_store_graph(clean_fact, get_user_dir(user_id))
            
            return WebhookResponse(
                action="saved",
                message="Got it.",
                stored_fact=clean_fact,
                doc_id=doc_id,
            )

        # Step 2b: BOTH — save the fact first, then answer the question
        if route == "BOTH":
            clean_fact = extraction_chain.invoke({"text": text, "today": today}).strip()
            doc_id     = save_to_memory(clean_fact, source, text, user_id)
            graph_engine.extract_and_store_graph(clean_fact, get_user_dir(user_id))
            
            # Now answer with the freshly updated memory
            query_embedding = embeddings.embed_query(text)
            rag_chain = build_dynamic_rag_chain(user_id, query_embedding)
            answer = rag_chain.invoke({"question": text, "history": history})
            log.info(f"BOTH route for [{user_id}]: saved '{clean_fact}' + answered")
            
            return WebhookResponse(
                action="answered",
                message=answer,
                stored_fact=clean_fact,
                doc_id=doc_id,
            )

        # Step 3: QUERY
        rag_chain = build_dynamic_rag_chain(user_id, query_embedding)
        answer = rag_chain.invoke({"question": text, "history": history})
        log.info(f"RAG answer for [{user_id}]: {answer}")
        
        return WebhookResponse(
            action="answered",
            message=answer,
        )
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={
            "action": "error",
            "message": f"An internal error occurred: {str(e)}",
            "error": str(e)
        })

# ── Web UI Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile(user_id: str = Depends(verify_token)):
    return load_profile_from_disk(user_id)

@app.post("/api/profile")
async def update_profile(profile: ProfilePayload, user_id: str = Depends(verify_token)):
    pf = get_profile_file(user_id)
    lock_file = pf.with_suffix('.lock')
    with FileLock(str(lock_file), timeout=5):
        with open(pf, "w") as f:
            json.dump(profile.model_dump(), f, indent=2)
    return {"status": "success"}

@app.get("/api/memories")
async def get_memories(user_id: str = Depends(verify_token)):
    memories = load_memory_from_disk(user_id)
    # Return newest first
    memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return memories

@app.delete("/api/memories/{doc_id}")
async def delete_memory_endpoint(doc_id: str, user_id: str = Depends(verify_token)):
    success = delete_from_memory(doc_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"action": "deleted", "doc_id": doc_id}

@app.post("/api/consolidate")
async def consolidate_memories(user_id: str = Depends(verify_token)):
    memories = load_memory_from_disk(user_id)
    if len(memories) < 2:
        return {"action": "skipped", "message": "Not enough memories to consolidate."}
        
    log.info(f"Running consolidation for user [{user_id}] on {len(memories)} memories...")
    
    # Chunk memories to prevent LLM context limit crashes
    chunk_size = 30
    consolidated_chunks = []
    
    for i in range(0, len(memories), chunk_size):
        chunk = memories[i:i + chunk_size]
        raw_text = "\n".join([f"- {m['fact']}" for m in chunk])
        res = consolidation_chain.invoke({"memories": raw_text}).strip()
        consolidated_chunks.append(res)
        
    # If there were multiple chunks, consolidate them one final time
    if len(consolidated_chunks) > 1:
        final_raw = "\n".join([f"- {c}" for c in consolidated_chunks])
        consolidated_fact = consolidation_chain.invoke({"memories": final_raw}).strip()
    else:
        consolidated_fact = consolidated_chunks[0]
    
    # Delete old memories
    for m in memories:
        delete_from_memory(m["id"], user_id)
        
    # Save new consolidated memory
    doc_id = save_to_memory(consolidated_fact, "consolidation", consolidated_fact, user_id)
    
    # Wipe the old graph to fix ghost nodes and rebuild it from the perfect summary
    user_dir = get_user_dir(user_id)
    graph_engine.wipe_graph(user_dir)
    graph_engine.extract_and_store_graph(consolidated_fact, user_dir)
    
    return {"action": "consolidated", "new_doc_id": doc_id, "consolidated_fact": consolidated_fact}

# Serve static files for the UI
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index_file = static_dir / "index.html"
    if index_file.exists():
        with open(index_file, "r") as f:
            return HTMLResponse(
                content=f.read(), 
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
            )
    return HTMLResponse(content="<h1>Kai Web UI</h1><p>static/index.html not found.</p>")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "assistant": "Kai Multi-Tenant",
        "llm": OPENAI_MODEL,
        "timestamp": datetime.utcnow().isoformat(),
    }
