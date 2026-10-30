FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM node:22.23.4-slim AS node

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

# Worker: local TTS, WhisperX alignment, Remotion + FFmpeg (D-24, D-26).
# Model files download into /models on first use, not into the image.
FROM deps AS worker
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fonts-dejavu-core \
      libnss3 libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 libgbm1 libasound2t64 \
      libxrandr2 libxkbcommon0 libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 \
      libcairo2 libcups2t64 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN uv sync --frozen --no-install-project --group media
COPY templates/remotion/package.json templates/remotion/package-lock.json templates/remotion/
RUN cd templates/remotion && npm ci --no-audit --no-fund && npx remotion browser ensure
ENV MODELS_DIR=/models TORCH_HOME=/models/torch HF_HOME=/models/hf
COPY . .
