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

import jwt
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError

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
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBED_MODEL      = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# Multi-tenant Auth config
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
JWT_SECRET           = os.getenv("JWT_SECRET", "super-secret-default-key-change-me")
SESSION_SECRET       = os.getenv("SESSION_SECRET", "super-secret-session-key-change-me")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Kai — Personal AI Assistant",
    description="Secure webhook with Multi-Tenant Agentic RAG and Web UI",
    version="3.0.0",
)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security & Auth (Google OAuth) ────────────────────────────────────────────

# Set up Authlib OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@app.get("/auth/login")
async def login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return JSONResponse(status_code=500, content={"error": "Google OAuth is not configured on the server."})
    
    # Generate the redirect URI dynamically
    redirect_uri = request.url_for('auth_callback')
    
    # Depending on proxy setup, we might need to enforce HTTPS scheme
    if "https" in str(request.url):
        redirect_uri = str(redirect_uri).replace("http://", "https://")
        
    return await oauth.google.authorize_redirect(request, str(redirect_uri))

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        if not user:
            raise HTTPException(status_code=400, detail="Could not fetch user info")
        
        # Issue a JWT token
        jwt_token = jwt.encode({
            "sub": user['email'], 
            "name": user.get('name', ''),
            "exp": datetime.utcnow().timestamp() + (30 * 24 * 3600) # 30 days
        }, JWT_SECRET, algorithm="HS256")
        
        # We redirect back to the home page, passing the token in the URL hash fragment
        # The frontend will extract it and put it in localStorage
        return RedirectResponse(url=f"/#token={jwt_token}")
    except OAuthError as error:
        return HTMLResponse(f'<h1>Error during OAuth</h1><p>{error.error}</p>')

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

--- Memory Context ---
{context}
--- End of Context ---

User question: {question}

Kai's answer:"""
)

# ── Chain Builders ────────────────────────────────────────────────────────────

router_chain     = ROUTER_PROMPT | llm | StrOutputParser()
extraction_chain = EXTRACTION_PROMPT | llm | StrOutputParser()

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

        # Step 1: Route
        route = router_chain.invoke({"text": text}).strip().upper()

        # Step 2a: SAVE
        if "SAVE" in route:
            clean_fact = extraction_chain.invoke({"text": text, "today": today}).strip()
            doc_id     = save_to_memory(clean_fact, source, text, user_id)
            return WebhookResponse(
                action="saved",
                message=f"Got it! I've saved that to memory: \"{clean_fact}\"",
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
    return sorted(memories, key=lambda x: x.get("timestamp", ""), reverse=True)

@app.delete("/api/memories/{doc_id}")
async def delete_memory_api(doc_id: str, user_id: str = Depends(verify_token)):
    success = delete_from_memory(doc_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
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
        "assistant": "Kai Multi-Tenant",
        "llm": OPENAI_MODEL,
        "timestamp": datetime.utcnow().isoformat(),
    }
