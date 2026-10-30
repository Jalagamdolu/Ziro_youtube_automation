FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12.16-slim AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# API + tests: no media stack (D-24).
FROM deps AS api
COPY . .

# Worker: local TTS + FFmpeg (D-24, D-25). Model files download into /models on first use.
FROM deps AS worker
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-install-project --group media
ENV MODELS_DIR=/models
COPY . .
