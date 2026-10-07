# NovelBridge backend — production image.
#
# Installs Python deps + the spaCy English NER model (en_core_web_sm, ~12 MB).
# The Chinese/Japanese spaCy models are NOT included (they add ~90 MB each and are off by
# default via NB_SOURCE_TERMS=false). Enable them per-deployment if needed.
#
# Build:
#   docker build -t novelbridge-backend .
#
# Run locally:
#   docker run -p 8000:8000 \
#     -e NB_ENGINE=mock \
#     -e NB_CORS_ORIGINS=http://localhost:5173 \
#     novelbridge-backend
#
# For Elastic Beanstalk the image is built by EB from this file; environment variables
# are set via the EB console or .ebextensions/ (see deploy/ docs).

FROM python:3.13-slim

WORKDIR /app

# --- system deps (spaCy needs a C compiler for its Cython extensions) -------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps ------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- spaCy English NER model (en_core_web_sm, ~12 MB) ----------------------
# Needed for POST /api/detect-names and POST /references/{id}/redetect.
# The zh/ja models are not installed here (kept off via NB_SOURCE_TERMS=false).
RUN python -m spacy download en_core_web_sm

# --- Application source -----------------------------------------------------
COPY app/ app/

# --- Runtime config ---------------------------------------------------------
# Defaults safe for a stateless hosted deployment (NB_STORAGE_BACKEND not needed
# here — storage choice is a frontend build-time variable). Override via EB env vars.
ENV NB_ENGINE=mock \
    OLLAMA_BASE_URL=http://localhost:11434 \
    OLLAMA_MODEL=qwen3.5:0.8b \
    OLLAMA_NUM_CTX=16384 \
    OLLAMA_NUM_THREAD=2 \
    OLLAMA_THINK=false \
    NB_CONTEXT_BUDGET_TOKENS=12000 \
    NB_MAX_CONCURRENT_TRANSLATIONS=3 \
    NB_QUEUE_TIMEOUT_SECONDS=30 \
    NB_DB_PATH=/tmp/novelbridge.db \
    NB_CORS_ORIGINS=http://localhost:5173 \
    NB_SOURCE_TERMS=false \
    NB_PRONOUN_CHECK=false

EXPOSE 8000

# Uvicorn bound to 0.0.0.0 so the container port is reachable from EB's proxy.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
