import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pdb_brands import router


class PdbBrandsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "pdb_brands_dictionary.parquet"
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
                "PDB_BRANDS_DICTIONARY_EDITS_PATH": str(
                    self.root / "pdb_brands_dictionary_edits.parquet"
                ),
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

    def test_uses_parquet_row_number_until_the_id_column_is_available(self):
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

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [row["record_key"] for row in response.json()["rows"]],
            ["row:0", "row:1"],
        )

    def test_modified_values_override_source_and_only_changes_are_persisted(self):
        response = self.update_raw("id:2", "Acme manually corrected")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["row"]["change_status"], "modified")

        occurrences = self.raw_search().json()["rows"]
        modified = next(row for row in occurrences if row["record_key"] == "id:2")
        self.assertEqual(modified["brand_raw"], "Acme manually corrected")
        self.assertEqual(modified["change_status"], "modified")
        self.assertNotIn("Acme, Inc.", [row["brand_raw"] for row in occurrences])

        edits = pq.read_table(
            self.root / "pdb_brands_dictionary_edits.parquet"
        ).to_pylist()
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["source_key"], "id:2")
        self.assertEqual(edits[0]["brand_raw"], "Acme manually corrected")
        source = pq.read_table(self.path).to_pylist()
        self.assertEqual(next(row for row in source if row["id"] == 2)["brand_raw"], "Acme, Inc.")

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

        edits = pq.read_table(
            self.root / "pdb_brands_dictionary_edits.parquet"
        ).to_pylist()
        self.assertEqual(len(edits), 1)
        self.assertIsNone(edits[0]["source_key"])
        self.assertTrue(edits[0]["is_new"])

    def test_rejects_cross_brand_or_unknown_record_updates(self):
        self.assertEqual(
            self.update_raw("id:2", "Wrong brand", brand="BETA").status_code,
            400,
        )
        self.assertEqual(self.update_raw("id:999", "Missing").status_code, 400)
        self.assertEqual(self.create_raw("Missing", brand="UNKNOWN").status_code, 400)


if __name__ == "__main__":
    unittest.main()
