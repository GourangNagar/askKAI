# Kai — Personal AI Assistant

> Secure FastAPI webhook · LangChain Agentic RAG · OpenAI GPT-4o-mini · ChromaDB · Hacker UI

Kai is a highly optimized, fully persistent personal AI assistant designed to remember facts, track expenses, and answer questions. It features a responsive edge-to-edge "Hacker Theme" mobile-first web UI, and uses advanced Retrieval-Augmented Generation (RAG) to maintain long-term memory.

---

## Features
- **Long-Term Memory:** Remembers facts, names, and numbers indefinitely using ChromaDB vector storage.
- **Smart Routing:** Automatically determines whether your input is a conversational question or a fact to save.
- **Mobile-First UI:** A sleek, edge-to-edge iOS-optimized "Hacker Theme" interface (Solid black, Neon Green).
- **Secure Webhooks:** Protected by a custom `WEBHOOK_SECRET` Bearer token.
- **Docker Ready:** Includes a `Dockerfile` for seamless deployment to Google Cloud Run, AWS, or local homelabs.

---

## Architecture

```
POST /webhook
   │
   ├── Bearer token check  (401 if invalid)
   │
   ├── LLM Router (OpenAI)  → SAVE | QUERY
   │
   ├── SAVE path
   │     └── Extraction chain → clean fact → ChromaDB (persist)
   │
   └── QUERY path
         └── Retriever (ChromaDB k=6) → RAG chain (OpenAI) → answer
```

---

## Quick Start (Local Setup)

### 1. Set up environment

```bash
# Clone the repository
git clone https://gitlab.com/gourang1/askkai.git
cd askkai

# Create .env file
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and WEBHOOK_SECRET
```

### 2. Install dependencies

```bash
# It is recommended to use a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Run the server

```bash
source .venv/bin/activate
# Load env variables and start the server
source .env 
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The Web UI will be available at: **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

---

## Docker Deployment

### Build

```bash
docker build -t kai:latest .
```

### Run Locally

```bash
docker run -d \
  --name kai \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your-openai-api-key" \
  -e WEBHOOK_SECRET="your-secret-token" \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  kai:latest
```

> The `-v` flag mounts the `/app/data` directory to your host so memory **persists across container restarts**.

### Deploy to Google Cloud Run

```bash
gcloud run deploy kai-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars="OPENAI_API_KEY=your-openai-api-key,WEBHOOK_SECRET=your-secret-token" \
  --execution-environment=gen2 \
  --add-volume=name=data-vol,type=cloud-storage,bucket=your-gcs-bucket-name \
  --add-volume-mount=volume=data-vol,mount-path=/app/data
```

---

## API Usage Example

### Save a fact / Add an expense

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "I spent $15 on lunch today at Subway."}'
```

**Response:**
```json
{
  "action": "saved",
  "message": "Got it! I've saved that to memory: \"Spent $15 on lunch at Subway today.\"",
  "stored_fact": "Spent $15 on lunch at Subway today.",
  "doc_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

### Ask a question

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "How much did I spend on lunch today?"}'
```

**Response:**
```json
{
  "action": "answered",
  "message": "You spent $15 on lunch at Subway today.",
  "stored_fact": null,
  "doc_id": null
}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key (`sk-proj-...`) |
| `WEBHOOK_SECRET` | ✅ | — | Bearer token for authentication |
| `OPENAI_MODEL` | ❌ | `gpt-4o-mini` | OpenAI Chat model name |
| `EMBED_MODEL` | ❌ | `text-embedding-3-small` | OpenAI Embedding model |

---

## Security Notes

- All API requests to `/webhook`, `/api/memories`, and `/api/profile` require a valid `Authorization: Bearer <token>` header.
- The web UI will prompt users for the Webhook Secret on first use and store it locally in the browser (`localStorage`).
- Never commit `.env` containing your real keys.
