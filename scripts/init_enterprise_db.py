from __future__ import annotations

import argparse
from pathlib import Path

from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the local SQLite enterprise demo database.")
    parser.add_argument("--db-path", default="data/enterprise_demo.db", help="SQLite database path.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the demo database file.")
    args = parser.parse_args()

    result = initialize_enterprise_demo_db(Path(args.db_path), reset=args.reset)
    print(result)


if __name__ == "__main__":
    main()

