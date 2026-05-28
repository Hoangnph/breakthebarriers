#!/bin/bash
set -e

echo "=== Initialising database schema ==="
python -c "
from backend.app.database import engine, Base
from backend.app import models_db
Base.metadata.create_all(bind=engine)
print('Schema ready.')
"

echo "=== Starting app ==="
exec "$@"
