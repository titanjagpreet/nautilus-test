"""``python -m strategy_lab.spec`` — write the spec's JSON Schema to ``strategy_lab/spec/schema.json``."""

from __future__ import annotations

import json
from pathlib import Path

from strategy_lab.spec.schema import json_schema


def main() -> None:
    path = Path(__file__).parent / "schema.json"
    path.write_text(json.dumps(json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
