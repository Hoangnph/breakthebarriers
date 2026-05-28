#!/bin/bash
# Production deploy script — chạy trên VPS
set -e

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"

echo "=== Pulling latest code ==="
git pull

echo "=== Building images ==="
docker compose $COMPOSE_FILES build --no-cache

echo "=== Starting services ==="
docker compose $COMPOSE_FILES up -d

echo "=== Running DB migration ==="
docker compose $COMPOSE_FILES exec app python backend/migrate_v2.py

echo "=== Deploy complete ==="
docker compose $COMPOSE_FILES ps
