from __future__ import annotations

import argparse
from pathlib import Path

from .backups import create_backup, restore_backup
from .database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(prog="vx-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Initialize the database")
    subparsers.add_parser("backup", help="Create an encrypted backup")
    restore = subparsers.add_parser(
        "restore", help="Restore an encrypted backup while the app is stopped"
    )
    restore.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
        print("Database initialized")
    elif args.command == "backup":
        print(create_backup())
    elif args.command == "restore":
        restore_backup(args.path)
        print("Backup restored")


if __name__ == "__main__":
    main()
