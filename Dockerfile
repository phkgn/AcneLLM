FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# Editable install keeps runtime templates/static files available from /app/src.
COPY src ./src
RUN python -m pip install --no-deps -e . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/config \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD python -c "import json,urllib.request as u; d=json.load(u.urlopen('http://localhost:8000/api/v1/health', timeout=5)); assert d['status']=='ok' and d['ollama'] and d['bm25_loaded'] and d['kb_chunks']>0"

CMD ["uvicorn", "acne_llm.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
