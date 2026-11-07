#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../backend"
PYTHON="${MEDSPACED_PYTHON:-../.venv/bin/python}"
export MEDSPACED_DATABASE_URL="sqlite:////tmp/medspaced-e2e.db"
export MEDSPACED_STORAGE_DIR="/tmp/medspaced-e2e-storage"
export MEDSPACED_SECRET_KEY="e2e-only-secret-key-with-enough-length"
export MEDSPACED_ENVIRONMENT="test"
export MEDSPACED_RATE_LIMIT_ENABLED="false"
export MEDSPACED_LOG_LEVEL="WARNING"

rm -f /tmp/medspaced-e2e.db
rm -rf /tmp/medspaced-e2e-storage
"$PYTHON" -m scripts.seed
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
