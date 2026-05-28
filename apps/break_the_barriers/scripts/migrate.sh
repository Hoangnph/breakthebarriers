#!/bin/bash
# Chạy DB migration trong container app đang chạy
set -e

echo "Running DB migration..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec app python backend/migrate_v2.py
echo "Migration complete."
