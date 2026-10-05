import json
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

from api.pdb_mc_classification import router


class PdbMcClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "pdb_mc_classification.parquet"
        self.runtime = self.root / "runtime_pdb_mc_classification.sqlite3"
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "master_code": "01_01_01",
                        "mc_desc": "Original one",
                        "family": "FAMILY A",
                        "subfamily": "SUB A",
                        "product_group": "GROUP A",
                    },
                    {
                        "master_code": "02_02_02",
                        "mc_desc": "Original two",
                        "family": "FAMILY B",
                        "subfamily": "SUB B",
                        "product_group": "GROUP B",
                    },
                ]
            ),
            self.source,
        )
        self.original_bytes = self.source.read_bytes()
        self.environment = patch.dict(
            os.environ,
            {
                "PDB_MC_CLASSIFICATION_LOCAL_PATH": str(self.source),
                "PDB_MC_CLASSIFICATION_RUNTIME_DB": str(self.runtime),
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
        return self.client.post(
            "/api/pdb/mc-classification/search",
            json={"page_size": 100, **payload},
        )

    def test_metadata_and_effective_join_keep_the_source_immutable(self):
        metadata = self.client.get("/api/pdb/mc-classification/metadata")
        self.assertEqual(metadata.status_code, 200, metadata.text)
        self.assertEqual(
            [column["field"] for column in metadata.json()["columns"]],
            ["master_code", "mc_desc", "family", "subfamily", "product_group"],
        )
        self.assertEqual(metadata.json()["families"], ["FAMILY A", "FAMILY B"])

        updated = self.client.patch(
            "/api/pdb/mc-classification/records",
            json={
                "record_key": "01_01_01",
                "values": {"mc_desc": "Edited", "family": "FAMILY C"},
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

        result = self.search(family="FAMILY C").json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["master_code"], "01_01_01")
        self.assertEqual(result["rows"][0]["mc_desc"], "Edited")
        self.assertEqual(result["rows"][0]["product_group"], "GROUP A")
        self.assertEqual(result["rows"][0]["__change_status"], "modified")
        self.assertEqual(self.search(family="FAMILY A").json()["total"], 0)

        second_update = self.client.patch(
            "/api/pdb/mc-classification/records",
            json={
                "record_key": "01_01_01",
                "values": {"product_group": "GROUP C"},
            },
        )
        self.assertEqual(second_update.status_code, 200, second_update.text)
        result = self.search(family="FAMILY C").json()
        self.assertEqual(result["rows"][0]["mc_desc"], "Edited")
        self.assertEqual(result["rows"][0]["product_group"], "GROUP C")
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

        with closing(sqlite3.connect(self.runtime)) as connection:
            stored = connection.execute(
                "SELECT values_json, is_new FROM classification_edits"
            ).fetchone()
        overlay = json.loads(stored[0])
        self.assertEqual(stored[1], 0)
        self.assertEqual(overlay["mc_desc"], "Edited")
        self.assertEqual(overlay["product_group"], "GROUP C")

    def test_new_rows_are_written_only_to_the_overlay_and_can_be_filtered(self):
        response = self.client.post(
            "/api/pdb/mc-classification/records",
            json={
                "values": {
                    "master_code": "03_03_03",
                    "mc_desc": "New row",
                    "family": "FAMILY C",
                    "subfamily": "SUB C",
                    "product_group": "GROUP C",
                }
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        result = self.search(subfamily="SUB C").json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["__change_status"], "added")
        self.assertEqual(self.search(search="new row").json()["total"], 1)

    def test_rejects_duplicate_or_changed_keys_and_unknown_filters(self):
        duplicate = self.client.post(
            "/api/pdb/mc-classification/records",
            json={"values": {"master_code": "01_01_01"}},
        )
        self.assertEqual(duplicate.status_code, 400)
        changed = self.client.patch(
            "/api/pdb/mc-classification/records",
            json={
                "record_key": "01_01_01",
                "values": {"master_code": "09_09_09"},
            },
        )
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(self.search(filters={"unknown": "x"}).status_code, 400)

    def test_missing_source_is_reported_without_creating_an_overlay(self):
        self.source.unlink()
        metadata = self.client.get("/api/pdb/mc-classification/metadata")
        self.assertFalse(metadata.json()["available"])
        response = self.search()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.runtime.exists())

    def test_migrates_the_legacy_parquet_overlay(self):
        legacy = self.root / "pdb_mc_classification_edits.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [{
                    "master_code": "01_01_01",
                    "mc_desc": "Migrated",
                    "family": "FAMILY C",
                    "subfamily": "SUB C",
                    "product_group": "GROUP C",
                }],
                schema=pq.read_schema(self.source),
            ),
            legacy,
        )

        result = self.search(family="FAMILY C")

        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["rows"][0]["mc_desc"], "Migrated")
        self.assertTrue(self.runtime.is_file())
        self.assertTrue(legacy.is_file())


if __name__ == "__main__":
    unittest.main()
