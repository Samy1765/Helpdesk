# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python API (serves the built frontend too) ----------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface
WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*

# CPU-only torch keeps the image small; then the rest of the requirements
COPY backend/requirements.txt ./
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# Bake the embedding model into the image so containers start offline
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend/ ./
COPY data/ /app/data/
COPY --from=frontend /frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
 && useradd --create-home --uid 10001 precision \
 && mkdir -p /app/faiss_indexes /app/data/uploads \
 && chown -R precision:precision /app
USER precision

ENV FRONTEND_DIST_DIR=/app/frontend/dist \
    FAISS_INDEX_DIR=/app/faiss_indexes \
    UPLOAD_DIR=/app/data/uploads \
    SERVICE_CATALOG_FILE=/app/data/service_catalog.json

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
ENTRYPOINT ["/entrypoint.sh"]
