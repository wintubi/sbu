"""CLI: structural validation for gold JSONL. Exit 0 only when all records pass."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.gold import validate_file  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/validate_gold.py <claims.jsonl>", file=sys.stderr)
        return 2
    result = validate_file(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
