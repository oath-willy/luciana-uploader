from __future__ import annotations

import math
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from services.codex_local_store import (
    CodexEnvironmentName,
    SnapshotUnavailable,
    SnapshotValidationError,
    codex_data_dir,
)
from services.codex_retrieval import MAX_LOOKUP_BATCH_SIZE, normalize_retrieval_description


LOCAL_RETRIEVER_VERSION = "pdb-bm25-local-v1"


def pdb_snapshot_path(environment: CodexEnvironmentName) -> Path:
    return codex_data_dir() / f"pdb-{environment}.sqlite3"


def pdb_environment_status() -> dict[str, bool]:
    return {
        environment: pdb_snapshot_path(environment).is_file()
        for environment in ("dev", "prod")
    }


class LocalPdbBm25Retriever:
    """Run the existing BM25 formula against an injected local SQLite PDB."""

    def __init__(self, environment: CodexEnvironmentName):
        self.environment = environment
        self.path = pdb_snapshot_path(environment)

    def metadata(self) -> dict[str, str]:
        with self._connect() as connection:
            return {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }

    def retrieve(self, items: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        normalized_items = list(items)
        if not normalized_items:
            return {}
        if len(normalized_items) > MAX_LOOKUP_BATCH_SIZE:
            raise ValueError(
                f"Seleziona al massimo {MAX_LOOKUP_BATCH_SIZE} record per analisi"
            )

        with self._connect() as connection:
            metadata = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }
            document_count = int(metadata.get("document_count", "0"))
            average_document_length = float(
                metadata.get("average_document_length", "0")
            )
            if document_count < 3 or average_document_length <= 0:
                raise RuntimeError("Snapshot PDB locale insufficiente per BS25")
            fallback = connection.execute(
                "SELECT * FROM pdb_items ORDER BY pdb_ref COLLATE NOCASE LIMIT 3"
            ).fetchall()

            result: dict[str, list[dict[str, Any]]] = {}
            for item in normalized_items:
                item_code = str(item.get("item_code") or "").strip()
                query_norm = normalize_retrieval_description(item.get("description") or "")
                if not item_code or not query_norm:
                    raise ValueError(
                        f"Item o descrizione vuota per {item_code or 'record CODEX'}"
                    )
                result[item_code] = self._retrieve_one(
                    connection,
                    query_norm,
                    document_count,
                    average_document_length,
                    fallback,
                )
        return result

    def _retrieve_one(
        self,
        connection: sqlite3.Connection,
        query_norm: str,
        document_count: int,
        average_document_length: float,
        fallback: list[sqlite3.Row],
    ) -> list[dict[str, Any]]:
        query_tokens = list(
            dict.fromkeys(token for token in query_norm.split() if len(token) >= 2)
        )
        document_frequency = {token: 0 for token in query_tokens}
        if query_tokens:
            placeholders = ",".join("?" for _ in query_tokens)
            rows = connection.execute(
                f"SELECT term, doc FROM pdb_vocab WHERE term IN ({placeholders})",
                query_tokens,
            ).fetchall()
            document_frequency.update({row["term"]: int(row["doc"]) for row in rows})

        seed_terms = sorted(
            (token for token in query_tokens if document_frequency[token] > 0),
            key=lambda token: (document_frequency[token], -len(token), token),
        )[:3]
        candidates_by_ref: dict[str, sqlite3.Row] = {
            row["pdb_ref"]: row for row in fallback
        }
        if seed_terms:
            match = " OR ".join(f'"{token}"' for token in seed_terms)
            rows = connection.execute(
                """
                SELECT item.*
                FROM pdb_fts
                INNER JOIN pdb_items AS item ON item.rowid = pdb_fts.rowid
                WHERE pdb_fts MATCH ?
                """,
                (match,),
            ).fetchall()
            candidates_by_ref.update({row["pdb_ref"]: row for row in rows})

        inverse_document_frequency = {
            token: math.log(
                1
                + (document_count - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            for token in query_tokens
        }
        maximum_bm25 = sum(inverse_document_frequency.values()) * 2.2
        scored: list[tuple[float, bool, str, dict[str, Any]]] = []
        for row in candidates_by_ref.values():
            tokens = str(row["pdb_norm"] or "").split()
            counts = Counter(tokens)
            document_length = len(tokens)
            raw_bm25 = 0.0
            for token in query_tokens:
                term_frequency = counts[token]
                if not term_frequency:
                    continue
                raw_bm25 += inverse_document_frequency[token] * (
                    term_frequency * 2.2
                ) / (
                    term_frequency
                    + 1.2
                    * (
                        0.25
                        + 0.75 * document_length / average_document_length
                    )
                )
            exact_match = str(row["pdb_norm"] or "") == query_norm
            identity_score = (
                int(exact_match)
                + min(raw_bm25 / maximum_bm25, 1.0)
                if maximum_bm25 > 0
                else int(exact_match)
            ) / 2
            proposal = {
                "identity_score": identity_score,
                "exact_match": exact_match,
                "pdb_ref": row["pdb_ref"],
                "pdb_description": row["pdb_description"],
                "manufacturer": row["manufacturer"],
                "father_name": row["father_name"],
                "pack": row["pack"],
                "feature": row["feature"],
                "measure": row["measure"],
                "master_code": row["master_code"],
                "retriever_version": LOCAL_RETRIEVER_VERSION,
            }
            scored.append((identity_score, exact_match, row["pdb_ref"], proposal))

        scored.sort(key=lambda entry: (-entry[0], not entry[1], entry[2].casefold()))
        proposals = []
        for rank, (_, _, _, proposal) in enumerate(scored[:3], start=1):
            proposals.append({**proposal, "identity_rank": rank})
        if len(proposals) != 3:
            raise RuntimeError(
                f"Il PDB locale ha restituito {len(proposals)} proposte, attese 3"
            )
        return proposals

    @contextmanager
    def _connect(self):
        if not self.path.is_file():
            raise SnapshotUnavailable(
                f"Snapshot PDB locale non disponibile: {self.path.name}"
            )
        connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def publish_pdb_snapshot(
    environment: CodexEnvironmentName,
    snapshot_id: str,
    created_at: str,
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build an atomically replaceable PDB index from an injected row stream."""
    if not snapshot_id.strip():
        raise SnapshotValidationError("snapshot_id PDB obbligatorio")
    target = pdb_snapshot_path(environment)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    row_count = 0
    token_count = 0
    seen: set[str] = set()
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=OFF;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE pdb_items (
                    pdb_ref TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    pdb_description TEXT,
                    manufacturer TEXT,
                    father_name TEXT,
                    pack TEXT,
                    feature TEXT,
                    measure TEXT,
                    master_code TEXT,
                    pdb_norm TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE pdb_fts USING fts5(
                    pdb_norm,
                    content='pdb_items',
                    content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 2'
                );
                CREATE VIRTUAL TABLE pdb_vocab USING fts5vocab(pdb_fts, 'row');
                """
            )
            batch = []
            for raw in rows:
                pdb_ref = str(
                    raw.get("pdb_ref") or raw.get("company_item_code") or ""
                ).strip()
                if not pdb_ref or pdb_ref.casefold() in seen:
                    continue
                description = str(
                    raw.get("pdb_description")
                    or raw.get("item_description_cleaned")
                    or ""
                )
                normalized = normalize_retrieval_description(description)
                if not normalized:
                    continue
                seen.add(pdb_ref.casefold())
                master_code = _master_code(raw)
                batch.append(
                    (
                        pdb_ref,
                        description,
                        raw.get("manufacturer")
                        or raw.get("manufacturer_company_name"),
                        raw.get("father_name"),
                        raw.get("pack"),
                        raw.get("feature"),
                        raw.get("measure"),
                        master_code,
                        normalized,
                    )
                )
                row_count += 1
                token_count += len(normalized.split())
                if len(batch) >= 5000:
                    connection.executemany(
                        "INSERT INTO pdb_items VALUES (?,?,?,?,?,?,?,?,?)", batch
                    )
                    batch.clear()
            if batch:
                connection.executemany(
                    "INSERT INTO pdb_items VALUES (?,?,?,?,?,?,?,?,?)", batch
                )
            if row_count < 3:
                raise SnapshotValidationError("Lo snapshot PDB richiede almeno 3 righe valide")
            connection.execute("INSERT INTO pdb_fts(pdb_fts) VALUES ('rebuild')")
            connection.execute("INSERT INTO pdb_fts(pdb_fts) VALUES ('optimize')")
            connection.executemany(
                "INSERT INTO metadata(key,value) VALUES (?,?)",
                [
                    ("snapshot_id", snapshot_id.strip()),
                    ("created_at", created_at),
                    ("published_at", _utc_now()),
                    ("environment", environment),
                    ("retriever_version", LOCAL_RETRIEVER_VERSION),
                    ("document_count", str(row_count)),
                    ("average_document_length", str(token_count / row_count)),
                ],
            )
            check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise SnapshotValidationError(f"SQLite quick_check PDB fallito: {check}")
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "environment": environment,
        "snapshot_id": snapshot_id.strip(),
        "rows": row_count,
        "retriever_version": LOCAL_RETRIEVER_VERSION,
        "path": str(target),
    }


def validate_and_publish_pdb_file(
    environment: CodexEnvironmentName, staged_path: Path
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{staged_path.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        required = {"metadata", "pdb_items", "pdb_fts", "pdb_vocab"}
        if not required.issubset(tables):
            raise SnapshotValidationError("File PDB locale con schema non valido")
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok":
            raise SnapshotValidationError(f"SQLite quick_check PDB fallito: {check}")
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if metadata.get("environment") != environment:
            raise SnapshotValidationError("Environment del file PDB non coerente")
        if metadata.get("retriever_version") != LOCAL_RETRIEVER_VERSION:
            raise SnapshotValidationError("Versione retriever PDB non supportata")
        row_count = connection.execute("SELECT COUNT(*) FROM pdb_items").fetchone()[0]
        if int(metadata.get("document_count", 0)) != row_count or row_count < 3:
            raise SnapshotValidationError("Conteggio righe PDB non coerente")
    finally:
        connection.close()
    target = pdb_snapshot_path(environment)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, target)
    return {
        "environment": environment,
        "snapshot_id": metadata.get("snapshot_id"),
        "rows": row_count,
        "retriever_version": metadata.get("retriever_version"),
        "path": str(target),
    }


def _master_code(row: dict[str, Any]) -> str | None:
    direct = str(row.get("master_code") or "").strip().upper()
    if direct:
        return direct
    levels = [row.get(f"mc_lvl{level}_code") for level in (1, 2, 3)]
    if any(value is None or str(value).strip() == "" for value in levels):
        return None
    return "_".join(str(value).strip().zfill(2) for value in levels)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
