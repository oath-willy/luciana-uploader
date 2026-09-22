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
            {"PDB_BRANDS_DICTIONARY_LOCAL_PATH": str(self.path)},
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
        self.assertEqual([row["id"] for row in occurrences["rows"]], [1, 3, 2])
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
        self.assertEqual([row["id"] for row in response.json()["rows"]], [0, 1])


if __name__ == "__main__":
    unittest.main()
