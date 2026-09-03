#!/usr/bin/env bash
set -Eeuo pipefail
APP_UID="$(id -u)"
APP_GID="$(id -g)"
DOCKER_BUILDKIT=0 docker build --tag short-video-short-video-app:latest .
env APP_UID="$APP_UID" APP_GID="$APP_GID" docker compose up -d --no-build
for attempt in $(seq 1 30); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' short-video-app 2>/dev/null || true)"
  if [ "$health" = "healthy" ] && curl --fail --silent --show-error http://127.0.0.1:8015/api/config >/dev/null; then
    echo "Deployment healthy."
    docker compose ps
    exit 0
  fi
  sleep 2
done
docker compose ps
docker compose logs --tail=100
echo "Deployment health check failed."
exit 1
