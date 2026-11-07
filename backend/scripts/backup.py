from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings

MANIFEST = "manifest.json"


class BackupError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pg_binary(name: str, pg_bin: Path | None = None) -> str:
    candidates = []
    if pg_bin is not None:
        candidates.append(Path(pg_bin) / name)
    configured = os.environ.get("MEDSPACED_PG_BIN")
    if configured:
        candidates.append(Path(configured) / name)
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    try:
        from embedded_postgres.postgres_server import POSTGRES_BIN_PATH

        candidate = POSTGRES_BIN_PATH / name
        if candidate.exists():
            return str(candidate)
    except ImportError:
        pass
    raise BackupError(f"{name} bulunamadı; MEDSPACED_PG_BIN ayarlayın")


def _pg_url(database_url: str) -> tuple[str, dict[str, str]]:
    url = make_url(database_url)
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    safe = url.set(drivername="postgresql").render_as_string(hide_password=True)
    return safe, env


def _sqlite_path(database_url: str) -> Path:
    url = make_url(database_url)
    if not url.database or url.database == ":memory:":
        raise BackupError("SQLite bellek veritabanı yedeklenemez")
    return Path(url.database)


def _sqlite_revision(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as con:
            row = con.execute("select version_num from alembic_version").fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def _postgres_revision(database_url: str) -> str | None:
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(database_url) as con:
            row = con.execute("select version_num from alembic_version").fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _copy_storage(storage_dir: Path, output: Path) -> int:
    if not storage_dir.exists():
        return 0
    count = 0
    with tarfile.open(output, "w:gz") as archive:
        for path in storage_dir.rglob("*"):
            if path.is_file():
                archive.add(path, arcname=str(Path("storage") / path.relative_to(storage_dir)))
                count += 1
    return count


def _restore_storage(archive: Path, storage_dir: Path) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(storage_dir.parent, filter="data")


def create_backup(
    *,
    output: Path,
    database_url: str | None = None,
    storage_dir: Path | None = None,
    pg_bin: Path | None = None,
) -> dict:
    database_url = database_url or settings.database_url
    storage_dir = storage_dir or settings.storage_path
    if output.exists():
        raise BackupError(f"Yedek dizini zaten var: {output}")
    output.mkdir(parents=True)
    url = make_url(database_url)
    manifest = {
        "created_at": _now(),
        "database_backend": url.get_backend_name(),
        "storage_files": 0,
        "alembic_revision": None,
    }

    if url.get_backend_name() == "sqlite":
        source = _sqlite_path(database_url)
        if not source.exists():
            raise BackupError(f"SQLite veritabanı bulunamadı: {source}")
        with sqlite3.connect(source) as src, sqlite3.connect(output / "db.sqlite") as dst:
            src.backup(dst)
        manifest["alembic_revision"] = _sqlite_revision(source)
    elif url.get_backend_name().startswith("postgresql"):
        safe_url, env = _pg_url(database_url)
        subprocess.run(
            [
                _pg_binary("pg_dump", pg_bin),
                "--format=custom",
                "--no-owner",
                f"--file={output / 'db.dump'}",
                f"--dbname={safe_url}",
            ],
            check=True,
            env=env,
        )
        manifest["alembic_revision"] = _postgres_revision(database_url)
    else:
        raise BackupError(f"Desteklenmeyen veritabanı: {url.get_backend_name()}")

    manifest["storage_files"] = _copy_storage(storage_dir, output / "storage.tar.gz")
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def restore_backup(
    *,
    archive: Path,
    database_url: str | None = None,
    storage_dir: Path | None = None,
    pg_bin: Path | None = None,
    force: bool = False,
) -> dict:
    database_url = database_url or settings.database_url
    storage_dir = storage_dir or settings.storage_path
    manifest_path = archive / MANIFEST
    if not manifest_path.exists():
        raise BackupError(f"Yedek manifestosu bulunamadı: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    url = make_url(database_url)

    if url.get_backend_name() == "sqlite":
        source = archive / "db.sqlite"
        if not source.exists():
            raise BackupError("Yedekte db.sqlite yok")
        target = _sqlite_path(database_url)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
    elif url.get_backend_name().startswith("postgresql"):
        dump = archive / "db.dump"
        if not dump.exists():
            raise BackupError("Yedekte db.dump yok")
        safe_url, env = _pg_url(database_url)
        subprocess.run(
            [
                _pg_binary("pg_restore", pg_bin),
                "--clean",
                "--if-exists",
                "--no-owner",
                f"--dbname={safe_url}",
                str(dump),
            ],
            check=True,
            env=env,
        )
    else:
        raise BackupError(f"Desteklenmeyen veritabanı: {url.get_backend_name()}")

    storage_archive = archive / "storage.tar.gz"
    if storage_archive.exists():
        if storage_dir.exists() and any(storage_dir.iterdir()) and not force:
            raise BackupError("Depolama dizini dolu; geri yüklemek için --force kullanın")
        _restore_storage(storage_archive, storage_dir)
    return manifest


def prune_backups(*, directory: Path, keep: int, dry_run: bool = False) -> list[Path]:
    if keep < 1:
        raise BackupError("keep en az 1 olmalı")
    if not directory.exists():
        return []
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / MANIFEST).exists()
        ),
        key=lambda path: (path / MANIFEST).stat().st_mtime,
        reverse=True,
    )
    stale = candidates[keep:]
    if not dry_run:
        for path in stale:
            shutil.rmtree(path)
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(description="MedSpaced veritabanı ve depolama yedeği")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--database-url")
    backup.add_argument("--storage-dir", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--database-url")
    restore.add_argument("--storage-dir", type=Path)
    restore.add_argument("--force", action="store_true")
    prune = sub.add_parser("prune")
    prune.add_argument("--directory", type=Path, required=True)
    prune.add_argument("--keep", type=int, default=14)
    prune.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = create_backup(
                output=args.output,
                database_url=args.database_url,
                storage_dir=args.storage_dir,
            )
        elif args.command == "restore":
            result = restore_backup(
                archive=args.input,
                database_url=args.database_url,
                storage_dir=args.storage_dir,
                force=args.force,
            )
        else:
            removed = prune_backups(
                directory=args.directory, keep=args.keep, dry_run=not args.apply
            )
            result = {
                "keep": args.keep,
                "dry_run": not args.apply,
                "removed": [str(path) for path in removed],
            }
    except (BackupError, subprocess.CalledProcessError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
