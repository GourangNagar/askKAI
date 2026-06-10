# Kai — Personal AI Assistant

> Secure FastAPI webhook · LangChain Agentic RAG · Gemini 1.5 Flash · ChromaDB

---

## Architecture

```
POST /webhook
   │
   ├── Bearer token check  (401 if invalid)
   │
   ├── LLM Router (Gemini)  → SAVE | QUERY
   │
   ├── SAVE path
   │     └── Extraction chain → clean fact → ChromaDB (persist)
   │
   └── QUERY path
         └── Retriever (ChromaDB k=6) → RAG chain (Gemini) → answer
```

---

## Quick Start (Local)

### 1. Set up environment

```bash
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY and WEBHOOK_SECRET
```

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the server

```bash
source .env  # or: export $(cat .env | xargs)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Server starts at **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

---

## Docker Deployment

### Build

```bash
docker build -t kai:latest .
```

### Run

```bash
docker run -d \
  --name kai \
  -p 8000:8000 \
  -e GOOGLE_API_KEY="your-api-key" \
  -e WEBHOOK_SECRET="your-secret-token" \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  kai:latest
```

> The `-v` flag mounts the data directory to your host so memory **persists across container restarts**.

### Logs

```bash
docker logs -f kai
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## API Usage

### Save a fact

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "I bought a 2BHK flat for 50.50 lakhs in Pune on 15 April 2026"}'
```

**Response:**
```json
{
  "action": "saved",
  "message": "Got it! I've saved that to memory: \"I purchased a 2BHK flat in Pune for ₹50.50 lakhs on 15 April 2026.\"",
  "stored_fact": "I purchased a 2BHK flat in Pune for ₹50.50 lakhs on 15 April 2026.",
  "doc_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

### Ask a question

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "How much did my flat cost?"}'
```

**Response:**
```json
{
  "action": "answered",
  "message": "Your 2BHK flat in Pune cost ₹50.50 lakhs, purchased on 15 April 2026.",
  "stored_fact": null,
  "doc_id": null
}
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | Google AI Studio API key |
| `WEBHOOK_SECRET` | ✅ | — | Bearer token for auth |
| `GEMINI_MODEL` | ❌ | `gemini-2.5-flash` | Gemini model name |
| `EMBED_MODEL` | ❌ | `models/gemini-embedding-001` | Google embedding model |

---

## Security Notes

- All `/webhook` requests require a valid `Authorization: Bearer <token>` header
- The container runs as a non-root user (`uid=1001`)
- Never commit `.env` — it is gitignored
- Generate a strong secret: `openssl rand -hex 32`
