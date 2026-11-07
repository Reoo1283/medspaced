import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    pytest.importorskip("embedded_postgres", reason="embedded-postgres kurulu değil") is None,
    reason="embedded-postgres kurulu değil",
)
def test_postgres_migrations_seed_and_downgrade(tmp_path: Path):
    from embedded_postgres import PostgresServer
    import psycopg

    server = PostgresServer(tmp_path / "pgdata", cleanup_mode="delete")
    try:
        server.psql("CREATE DATABASE medspaced;")
        url = server.get_uri("medspaced").replace("postgresql://", "postgresql+psycopg://", 1)
        env = dict(
            os.environ,
            MEDSPACED_DATABASE_URL=url,
            MEDSPACED_STORAGE_DIR=str(tmp_path / "storage"),
            MEDSPACED_SECRET_KEY="migration-test-secret-at-least-32-chars",
            MEDSPACED_ENVIRONMENT="test",
        )
        alembic = [sys.executable, "-m", "alembic"]
        subprocess.run([*alembic, "upgrade", "head"], env=env, check=True)
        subprocess.run([sys.executable, "-m", "scripts.seed"], env=env, check=True)

        raw_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as con:
            assert con.execute("select version_num from alembic_version").fetchone()[0] == "8f2c1d9b7a10"
            assert con.execute("select count(*) from users").fetchone()[0] == 3
            assert con.execute("select count(*) from exercises").fetchone()[0] == 8

        subprocess.run([*alembic, "downgrade", "-1"], env=env, check=True)
        with psycopg.connect(raw_url) as con:
            assert con.execute("select to_regclass('public.user_learning_settings')").fetchone()[0] is None
            assert con.execute("select version_num from alembic_version").fetchone()[0] == "e6e3eefa062a"

        subprocess.run([*alembic, "upgrade", "head"], env=env, check=True)
        with psycopg.connect(raw_url) as con:
            assert con.execute("select to_regclass('public.user_learning_settings')").fetchone()[0] is not None
    finally:
        server.cleanup()
