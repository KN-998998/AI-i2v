# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8015 \
    APP_RELOAD=false

WORKDIR /app

# FFmpeg is required by the compose and media-preview services.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY web/ ./web/
COPY pipeline/ ./pipeline/
COPY docs/ ./docs/
COPY README.md AGENTS.md pytest.ini ./
COPY --from=frontend-build /app/web/static/canvas-app/ ./web/static/canvas-app/

RUN mkdir -p /app/output /app/logs \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app

USER app

EXPOSE 8015

CMD ["python", "-m", "web.run_server"]
