import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pdb_settings import router
from services.mc_code_local_store import McCodeSnapshotStore, SnapshotValidationError, publish_snapshot
from services.pdb_new_items_sync import (
    build_new_items_snapshot, new_items_job_store, new_items_status, run_new_items_sync,
)


class NewItemsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "MC_CODE_LOCAL_DATA_DIR": str(self.root),
            "MC_CODE_RUNTIME_DB": str(self.root / "runtime.sqlite3"),
        })
        self.env.start()
        publish_snapshot("dev", "old", "2026-09-14", [{"company": "ACME"}], [{
            "company": "ACME", "item_code": "001", "description": "old",
            "bs25_selected_proposal_rank": 1, "bs25_selected_master_code": "01_02_03",
        }], [{"master_code": "01_02_03", "components": {}}])
        self.parquet = self.root / "fixture.parquet"
        pq.write_table(pa.Table.from_pylist([{
            "company": "ACME", "item_code": "001", "description": "new description",
            "item_extra_descriptions": json.dumps({"manufacturer": ["Maker"], "customer_raw": ["Alpha", "Beta"]}),
        }, {
            "company": "OTHER", "item_code": "002", "description": "other",
            "item_extra_descriptions": "{}",
        }]), self.parquet)
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_refresh_updates_companies_details_and_preserves_selection(self):
        blob = Mock()
        blob.__enter__ = Mock(return_value=blob)
        blob.__exit__ = Mock(return_value=False)
        props = Mock(size=self.parquet.stat().st_size, etag='"test-etag"')
        blob.get_blob_properties.return_value = props
        blob.download_blob.return_value.readinto.side_effect = lambda stream: stream.write(self.parquet.read_bytes())
        with patch("services.pdb_new_items_sync._blob_client", return_value=blob):
            response = self.client.post("/api/pdb/settings/new-items/refresh")
        self.assertEqual(response.status_code, 202)
        status = self.client.get("/api/pdb/settings/new-items").json()
        self.assertEqual(status["job"]["status"], "completed")
        self.assertEqual(status["file"]["name"], "pdb_new_items.parquet")
        self.assertEqual(status["job"]["row_count"], 2)
        self.assertEqual(status["copies"], {"backend": True})
        store = McCodeSnapshotStore("dev")
        self.assertEqual([c["value"] for c in store.companies()], ["ACME", "OTHER"])
        result = store.search("ACME", "full", 0, 25, "", {"customer_raw": "Beta"})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["manufacturer"], ["Maker"])
        self.assertEqual(result["rows"][0]["bs25_selected_master_code"], "01_02_03")
        self.assertEqual(store.metadata()["source_file"], "pdb_new_items.parquet")
        self.assertEqual(store.search("ACME", "full", 1, 1, "", {})["rows"], [])

    def test_failed_download_retains_current_dataset(self):
        request_id = "failed"
        new_items_job_store().claim(request_id, "test")
        with patch("services.pdb_new_items_sync._blob_client", side_effect=RuntimeError("offline")):
            run_new_items_sync(request_id)
        self.assertEqual(new_items_status()["job"]["status"], "failed")
        self.assertFalse(new_items_status()["file"]["available"])
        self.assertEqual(new_items_status()["copies"], {"backend": False})
        self.assertEqual(McCodeSnapshotStore("dev").metadata()["snapshot_id"], "old")

    def test_bad_json_and_duplicates_are_rejected_before_publication(self):
        for rows in ([{
            "company": "ACME", "item_code": "1", "description": "x", "item_extra_descriptions": "bad",
        }], [
            {"company": "ACME", "item_code": "1", "description": "x"},
            {"company": "ACME", "item_code": "1", "description": "y"},
        ]):
            pq.write_table(pa.Table.from_pylist(rows), self.parquet)
            with self.assertRaises(SnapshotValidationError):
                build_new_items_snapshot(self.parquet, self.root / "staged.sqlite3", "new")
            self.assertEqual(McCodeSnapshotStore("dev").metadata()["snapshot_id"], "old")

    def test_second_refresh_is_rejected_while_active(self):
        new_items_job_store().claim("active", "test")
        self.assertEqual(self.client.post("/api/pdb/settings/new-items/refresh").status_code, 409)


if __name__ == "__main__":
    unittest.main()
