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

# 1. Pin to a specific minor patch version for supply-chain security
FROM python:3.13.1-slim

# 2. Setup environment optimizations
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/app/.local/bin:${PATH}"

# 3. Securely create the system user first
RUN groupadd --system app \
    && useradd --system \
        --gid app \
        --create-home \
        --home-dir /home/app \
        app

# 4. Set workdir and establish safe user ownership early
WORKDIR /home/app/workspace
RUN chown app:app /home/app/workspace

# 5. Drop down to the non-root user immediately for all installations
USER app

# 6. Install dependencies into the user's local space
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 7. Download spaCy model securely as the non-root user
RUN python -m spacy download en_core_web_sm

# 8. Copy application source with strict permissions
COPY --chown=app:app app/ app/

# 9. Minimal runtime environment fallback configurations.
ENV NB_ENGINE=mock \
    NB_DB_PATH=/home/app/novelbridge.db

EXPOSE 8000

# 10. Run via Uvicorn safely bound to port
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

