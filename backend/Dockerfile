# Nexus backend — Cloud Run image (see /DEPLOY.md).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/tmp/hf

# Docling (PDF/DOCX → Markdown) needs these shared libs at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install from the lock file. Torch comes from the CPU-only index and the CUDA wheels
# (nvidia-*, triton) are dropped — Cloud Run has no GPU, and they add ~4 GB.
COPY pyproject.toml poetry.lock ./
RUN pip install "poetry==1.8.4" \
 && poetry export --only main --without-hashes -o /tmp/req.txt \
 && grep -viE '^(nvidia-|triton)' /tmp/req.txt \
    | sed -E 's/^(torch(vision)?==[0-9.]+)/\1+cpu/' > /tmp/req-cpu.txt \
 && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/req-cpu.txt \
 && pip uninstall -y poetry

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Migrations run on boot (the service is capped at one instance, so no race).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
