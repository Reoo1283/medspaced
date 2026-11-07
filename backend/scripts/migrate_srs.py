#!/usr/bin/env python
"""SM-2 -> FSRS migration CLI tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal, init_db
from app.services.srs_migration import (
    apply_srs_migration,
    plan_srs_migration,
    rollback_srs_migration,
    validate_srs_migration,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="SM-2 -> FSRS migration tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Plan the migration")
    plan_parser.add_argument("--limit", type=int, default=None, help="Limit candidates")
    plan_parser.add_argument("--json", action="store_true", help="Output JSON")

    apply_parser = subparsers.add_parser("apply", help="Apply the migration")
    apply_parser.add_argument("--limit", type=int, default=None, help="Limit candidates")
    apply_parser.add_argument("--batch-id", type=str, default=None, help="Custom batch ID")
    apply_parser.add_argument("--json", action="store_true", help="Output JSON")

    validate_parser = subparsers.add_parser("validate", help="Validate a migration batch")
    validate_parser.add_argument("--batch-id", type=str, default=None, help="Batch ID to validate")
    validate_parser.add_argument("--json", action="store_true", help="Output JSON")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback a migration batch")
    rollback_parser.add_argument("--batch-id", type=str, required=True, help="Batch ID to rollback")
    rollback_parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.command == "plan":
            result = plan_srs_migration(db, limit=args.limit)
        elif args.command == "apply":
            result = apply_srs_migration(db, limit=args.limit, batch_id=args.batch_id)
        elif args.command == "validate":
            result = validate_srs_migration(db, batch_id=args.batch_id)
        elif args.command == "rollback":
            result = rollback_srs_migration(db, batch_id=args.batch_id)
        else:
            parser.error(f"Unknown command: {args.command}")
            return 1

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())