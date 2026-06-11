"""
Kai — Personal AI Assistant
FastAPI webhook server with LangChain Agentic RAG, OpenAI, ChromaDB, and Google OAuth Multi-Tenancy.
"""

import os
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import secrets
import random

import jwt
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import bcrypt

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from semantic_router import SemanticRouter
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
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
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
    phrase_words = [random.choice(WORDLIST) for _ in range(12)]
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
        with open(pf, "w") as f:
            json.dump({"name": payload.name, "instructions": "I prefer concise and direct answers."}, f, indent=2)
    
    # Generate JWT
    jwt_token = jwt.encode({
        "sub": email, 
        "exp": datetime.utcnow().timestamp() + (30 * 24 * 3600)
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
vectorstore = Chroma(embedding_function=embeddings)

semantic_router = SemanticRouter(embeddings)
graph_engine = GraphEngine(llm)

def get_user_dir(user_id: str) -> Path:
    # Use email as folder name (sanitize it for filesystem safety)
    safe_id = "".join(c for c in user_id if c.isalnum() or c in ('@', '.', '-', '_'))
    user_dir = DATA_DIR / safe_id
    user_dir.mkdir(exist_ok=True)
    return user_dir

def get_memory_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "memory.json"

def get_profile_file(user_id: str) -> Path:
    return get_user_dir(user_id) / "profile.json"

def load_profile_from_disk(user_id: str) -> dict:
    pf = get_profile_file(user_id)
    if pf.exists():
        with open(pf, "r") as f:
            return json.load(f)
    return {"name": "User", "instructions": "I prefer concise and direct answers."}

def load_memory_from_disk(user_id: str) -> list:
    mf = get_memory_file(user_id)
    if mf.exists():
        with open(mf, "r") as f:
            return json.load(f)
    return []

def save_memory_to_disk(memories: list, user_id: str):
    mf = get_memory_file(user_id)
    with open(mf, "w") as f:
        json.dump(memories, f, indent=2)

def sync_all_memory_to_chroma():
    log.info("Loading all tenant memories into ChromaDB...")
    docs = []
    ids = []
    
    # Iterate through all user directories in data/
    for user_dir in DATA_DIR.iterdir():
        if user_dir.is_dir():
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

sync_all_memory_to_chroma()

def save_to_memory(fact: str, source: str, original: str, user_id: str) -> str:
    doc_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
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

--- Memory Context (Vectors) ---
{context}

--- Relational Graph Context (Entities) ---
{graph_context}
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

def build_dynamic_rag_chain(user_id: str):
    # Dynamic retriever locked to the specific user namespace
    retriever = vectorstore.as_retriever(
        search_type="similarity", 
        search_kwargs={"k": 6, "filter": {"user_id": user_id}}
    )
    
    def format_docs(docs):
        return "\n\n".join(
            f"[Memory {i+1}]: {d.page_content}" for i, d in enumerate(docs)
        )

    def load_profile(_):
        p = load_profile_from_disk(user_id)
        return f"User Name: {p.get('name', 'User')}\nInstructions: {p.get('instructions', '')}"

    return (
        {
            "context":  retriever | format_docs,
            "graph_context": lambda question: graph_engine.query_graph(question, get_user_dir(user_id)),
            "question": RunnablePassthrough(),
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
        today  = datetime.now().strftime("%A, %d %B %Y")

        log.info(f"Received payload | user={user_id} | source={source} | text={text!r}")

        if not text:
            return JSONResponse(status_code=400, content={"error": "'text' field must not be empty.", "action": "error", "message": "Empty text"})

        # Step 1: Route using Semantic Vectors (No LLM)
        route = semantic_router.route_intent(text)

        # Step 2a: SAVE
        if "SAVE" in route:
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

        # Step 2b: QUERY
        rag_chain = build_dynamic_rag_chain(user_id)
        answer = rag_chain.invoke(text)
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
        
    raw_memories_text = "\n".join([f"- {m['fact']}" for m in memories])
    
    log.info(f"Running consolidation for user [{user_id}] on {len(memories)} memories...")
    
    # Run LLM consolidation
    consolidated_fact = consolidation_chain.invoke({"memories": raw_memories_text}).strip()
    
    # Delete old memories
    for m in memories:
        delete_from_memory(m["id"], user_id)
        
    # Save the new thick block
    new_doc_id = save_to_memory(consolidated_fact, source="consolidation", original=raw_memories_text, user_id=user_id)
    
    log.info(f"Consolidation complete. Created block {new_doc_id}")
    return {"action": "consolidated", "new_doc_id": new_doc_id, "consolidated_fact": consolidated_fact}

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
