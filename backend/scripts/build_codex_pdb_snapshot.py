"""Build the local BS25 SQLite index from an injected CSV or JSONL PDB dump."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.codex_local_retrieval import publish_pdb_snapshot  # noqa: E402


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            yield handle
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            yield handle


def _rows(path: Path, input_format: str) -> Iterator[dict[str, Any]]:
    with _open_text(path) as handle:
        if input_format == "csv":
            yield from csv.DictReader(handle)
            return
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Riga JSONL {line_number} non valida")
            yield value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--environment", choices=("dev", "prod"), default="dev")
    parser.add_argument("--format", choices=("csv", "jsonl"))
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    detected_format = args.format or (
        "jsonl" if ".jsonl" in source.name.lower() else "csv"
    )
    created_at = datetime.now(timezone.utc).isoformat()
    receipt = publish_pdb_snapshot(
        args.environment,
        args.snapshot_id or f"{source.stem}-{created_at}",
        created_at,
        _rows(source, detected_format),
    )
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
