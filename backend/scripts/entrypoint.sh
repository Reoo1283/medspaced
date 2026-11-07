#!/bin/sh
set -eu

if [ "${MEDSPACED_RUN_MIGRATIONS:-true}" = "true" ]; then
    python -m alembic upgrade head
fi

exec "$@"
