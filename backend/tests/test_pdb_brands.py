import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pdb_brands import router
from services.pdb_brands import EDITS_SCHEMA


class PdbBrandsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "pdb_brands_dictionary.parquet"
        self.workspace = self.root / "pdb_brands_dictionary_workspace.sqlite3"
        self.legacy_runtime = self.root / "runtime_pdb_brands_dictionary.sqlite3"
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {"id": 1, "brand_raw": "Acme Incorporated", "brand": "ACME", "prefix": "AC"},
                    {"id": 2, "brand_raw": "Acme, Inc.", "brand": "ACME", "prefix": "A2"},
                    {"id": 3, "brand_raw": "Acme Incorporated", "brand": "ACME", "prefix": "AC"},
                    {"id": 4, "brand_raw": "Beta raw", "brand": "BETA", "prefix": "BT"},
                    {"id": 5, "brand_raw": "Ignored", "brand": "", "prefix": "XX"},
                ]
            ),
            self.path,
        )
        self.environment = patch.dict(
            os.environ,
            {
                "PDB_BRANDS_DICTIONARY_LOCAL_PATH": str(self.path),
                "PDB_BRANDS_DICTIONARY_WORKSPACE_DB": str(self.workspace),
                "PDB_BRANDS_DICTIONARY_RUNTIME_DB": str(self.legacy_runtime),
            },
        )
        self.environment.start()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def search(self, **payload):
        return self.client.post("/api/pdb/brands/search", json=payload)

    def raw_search(self, brand="ACME", **payload):
        return self.client.post(
            "/api/pdb/brands/raw/search",
            json={"brand": brand, **payload},
        )

    def update_raw(self, record_key, brand_raw, brand="ACME"):
        return self.client.patch(
            "/api/pdb/brands/raw/records",
            json={
                "record_key": record_key,
                "brand": brand,
                "brand_raw": brand_raw,
            },
        )

    def create_raw(self, brand_raw, brand="ACME"):
        return self.client.post(
            "/api/pdb/brands/raw/records",
            json={"brand": brand, "brand_raw": brand_raw},
        )

    def test_lists_unique_brand_column_values_with_aggregated_prefixes(self):
        response = self.search()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            data["rows"],
            [
                {"brand": "ACME", "prefix": "A2, AC"},
                {"brand": "BETA", "prefix": "BT"},
            ],
        )

    def test_filters_and_returns_every_brand_raw_occurrence(self):
        self.assertEqual(self.search(search="beta").json()["rows"][0]["brand"], "BETA")
        self.assertEqual(
            self.search(filters={"prefix": "A2"}).json()["rows"][0]["brand"],
            "ACME",
        )

        occurrences = self.raw_search().json()
        self.assertEqual(occurrences["total"], 3)
        self.assertEqual(
            [row["record_key"] for row in occurrences["rows"]],
            ["id:1", "id:3", "id:2"],
        )
        self.assertEqual(
            self.raw_search(filters={"brand_raw": "Inc."}).json()["total"],
            1,
        )

    def test_missing_file_and_invalid_filters_are_reported(self):
        self.assertEqual(self.search(filters={"unknown": "x"}).status_code, 400)
        self.path.unlink()
        response = self.search()
        self.assertEqual(response.status_code, 503)
        self.assertIn("PDB Settings", response.json()["detail"])

    def test_rejects_a_dictionary_without_the_id_column(self):
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {"brand_raw": "Legacy A", "brand": "LEGACY", "prefix": "LG"},
                    {"brand_raw": "Legacy B", "brand": "LEGACY", "prefix": "LG"},
                ]
            ),
            self.path,
        )

        response = self.raw_search(brand="LEGACY")

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("id", response.json()["detail"])

    def test_rejects_null_non_integer_or_duplicate_ids(self):
        invalid_rows = [
            {"id": 1, "brand_raw": "A", "brand": "ACME", "prefix": "AC"},
            {"id": None, "brand_raw": "B", "brand": "ACME", "prefix": "AC"},
        ]
        pq.write_table(pa.Table.from_pylist(invalid_rows), self.path)
        response = self.raw_search()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("interi non nulli", response.json()["detail"])

        duplicate_rows = [
            {"id": 1, "brand_raw": "A", "brand": "ACME", "prefix": "AC"},
            {"id": 1, "brand_raw": "B", "brand": "ACME", "prefix": "AC"},
        ]
        pq.write_table(pa.Table.from_pylist(duplicate_rows), self.path)
        response = self.raw_search()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("univoca", response.json()["detail"])

    def test_modified_values_override_source_and_only_changes_are_persisted(self):
        response = self.update_raw("id:2", "Acme manually corrected")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["row"]["change_status"], "modified")

        occurrences = self.raw_search().json()["rows"]
        modified = next(row for row in occurrences if row["record_key"] == "id:2")
        self.assertEqual(modified["brand_raw"], "Acme manually corrected")
        self.assertEqual(modified["change_status"], "modified")
        self.assertNotIn("Acme, Inc.", [row["brand_raw"] for row in occurrences])

        with closing(sqlite3.connect(self.workspace)) as connection:
            edits = connection.execute(
                "SELECT source_id, brand_raw FROM brand_edits"
            ).fetchall()
        self.assertEqual(edits, [(2, "Acme manually corrected")])
        self.assertEqual(response.json()["workspace_file"], self.workspace.name)
        source = pq.read_table(self.path).to_pylist()
        self.assertEqual(next(row for row in source if row["id"] == 2)["brand_raw"], "Acme, Inc.")

    def test_override_stays_attached_to_id_when_source_rows_are_reordered(self):
        response = self.update_raw("id:2", "Stable override")
        self.assertEqual(response.status_code, 200, response.text)
        source_rows = list(reversed(pq.read_table(self.path).to_pylist()))
        pq.write_table(pa.Table.from_pylist(source_rows), self.path)

        occurrences = self.raw_search().json()["rows"]

        modified = next(row for row in occurrences if row["source_id"] == 2)
        self.assertEqual(modified["record_key"], "id:2")
        self.assertEqual(modified["brand_raw"], "Stable override")
        self.assertEqual(modified["change_status"], "modified")

    def test_override_follows_id_when_the_source_brand_changes(self):
        response = self.update_raw("id:2", "Stable override")
        self.assertEqual(response.status_code, 200, response.text)
        source_rows = pq.read_table(self.path).to_pylist()
        next(row for row in source_rows if row["id"] == 2)["brand"] = "BETA"
        pq.write_table(pa.Table.from_pylist(source_rows), self.path)

        beta_rows = self.raw_search(brand="BETA").json()["rows"]
        modified = next(row for row in beta_rows if row["source_id"] == 2)
        self.assertEqual(modified["brand_raw"], "Stable override")
        self.assertEqual(
            self.update_raw("id:2", "Updated again", brand="BETA").status_code,
            200,
        )

    def test_new_occurrences_are_stored_in_overlay_and_can_be_modified(self):
        created = self.create_raw("New manual occurrence")
        self.assertEqual(created.status_code, 200, created.text)
        record_key = created.json()["row"]["record_key"]
        self.assertTrue(record_key.startswith("new:"))

        updated = self.update_raw(record_key, "Updated manual occurrence")
        self.assertEqual(updated.status_code, 200, updated.text)
        occurrences = self.raw_search().json()
        self.assertEqual(occurrences["total"], 4)
        added = next(
            row for row in occurrences["rows"] if row["record_key"] == record_key
        )
        self.assertEqual(added["brand_raw"], "Updated manual occurrence")
        self.assertEqual(added["change_status"], "added")

        with closing(sqlite3.connect(self.workspace)) as connection:
            edits = connection.execute(
                "SELECT source_id, is_new FROM brand_edits"
            ).fetchall()
        self.assertEqual(edits, [(None, 1)])

    def test_rejects_cross_brand_or_unknown_record_updates(self):
        self.assertEqual(
            self.update_raw("id:2", "Wrong brand", brand="BETA").status_code,
            400,
        )
        self.assertEqual(self.update_raw("id:999", "Missing").status_code, 400)
        self.assertEqual(self.create_raw("Missing", brand="UNKNOWN").status_code, 400)

    def test_migrates_the_legacy_parquet_overlay(self):
        legacy = self.root / "pdb_brands_dictionary_edits.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [{
                    "record_key": "id:2",
                    "source_key": "id:2",
                    "brand": "ACME",
                    "brand_raw": "Migrated value",
                    "is_new": False,
                    "updated_at": "2026-09-22T10:00:00+00:00",
                }],
                schema=EDITS_SCHEMA,
            ),
            legacy,
        )

        response = self.raw_search()

        self.assertEqual(response.status_code, 200, response.text)
        migrated = next(
            row for row in response.json()["rows"] if row["record_key"] == "id:2"
        )
        self.assertEqual(migrated["brand_raw"], "Migrated value")
        self.assertTrue(self.workspace.is_file())
        self.assertTrue(legacy.is_file())

        with closing(sqlite3.connect(self.workspace)) as connection:
            stored = connection.execute(
                "SELECT source_id, brand_raw FROM brand_edits"
            ).fetchall()
        self.assertEqual(stored, [(2, "Migrated value")])

    def test_migrates_the_previous_sqlite_runtime_to_source_id(self):
        with closing(sqlite3.connect(self.legacy_runtime)) as connection:
            connection.execute(
                """
                CREATE TABLE brand_edits (
                    record_key TEXT PRIMARY KEY,
                    source_key TEXT UNIQUE,
                    brand TEXT NOT NULL,
                    brand_raw TEXT NOT NULL,
                    is_new INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO brand_edits VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "id:2",
                    "id:2",
                    "ACME",
                    "Migrated from SQLite",
                    0,
                    "2026-09-22T10:00:00+00:00",
                ),
            )
            connection.commit()

        response = self.raw_search()

        self.assertEqual(response.status_code, 200, response.text)
        migrated = next(
            row for row in response.json()["rows"] if row["source_id"] == 2
        )
        self.assertEqual(migrated["brand_raw"], "Migrated from SQLite")
        with closing(sqlite3.connect(self.workspace)) as connection:
            stored = connection.execute(
                "SELECT source_id FROM brand_edits"
            ).fetchall()
        self.assertEqual(stored, [(2,)])


if __name__ == "__main__":
    unittest.main()
