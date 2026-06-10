# ─────────────────────────────────────────────────────────────────────────────
#  Kai — Personal AI Assistant
#  Multi-stage Dockerfile
#  Stage 1: builder  — installs deps into a venv
#  Stage 2: runtime  — lean final image
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed for chromadb native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip, install wheel first to avoid build failures
RUN pip install --upgrade pip wheel setuptools

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Kai Assistant" \
    description="Personal AI Assistant — FastAPI + LangChain + ChromaDB + Gemini"

WORKDIR /app

# Runtime system deps (sqlite3 is needed by chromadb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder stage (no build tools in final image)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN groupadd --gid 1001 kai && \
    useradd  --uid 1001 --gid 1001 --no-create-home kai

# Data persistent storage volume (replaces chroma_db)
RUN mkdir -p /app/data && chown -R kai:kai /app/data
VOLUME ["/app/data"]

# Copy application source and static UI
COPY main.py .
COPY static ./static

# Drop privileges
USER kai

# Override at runtime:  docker run -e OPENAI_API_KEY=... -e WEBHOOK_SECRET=...
ENV OPENAI_MODEL=gpt-4o-mini \
    EMBED_MODEL=text-embedding-3-small

# Healthcheck using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Start Uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
