import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pdb_settings import router
from services.pdb_ref_sync import PdbRefSyncStore, pdb_ref_status, run_pdb_ref_sync


class PdbSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.key_path = self.data_dir / "key.pem"
        self.key_path.write_text("fixture", encoding="utf-8")
        self.environment_patch = patch.dict(
            os.environ,
            {
                "MC_CODE_LOCAL_DATA_DIR": str(self.data_dir),
                "PDB_REF_STATUS_DB": str(self.data_dir / "pdb-settings.sqlite3"),
                "PDB_REF_LOCAL_PATH": str(self.data_dir / "ref_pdb_dump.parquet"),
                "PDB_REF_SSH_PRIVATE_KEY_PATH": str(self.key_path),
            },
        )
        self.environment_patch.start()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.environment_patch.stop()
        self.temporary.cleanup()

    def test_status_and_refresh_are_persisted(self):
        status = self.client.get("/api/pdb/settings/ref-dump")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["file"]["available"])

        with patch("api.pdb_settings.run_pdb_ref_sync") as runner:
            started = self.client.post("/api/pdb/settings/ref-dump/refresh")
        blocked = self.client.post("/api/pdb/settings/ref-dump/refresh")

        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.json()["job"]["status"], "queued")
        runner.assert_called_once()
        self.assertEqual(blocked.status_code, 409)

    def test_sync_records_fetch_download_and_index_outcome(self):
        request_id = "sync-request-1"
        self.assertTrue(PdbRefSyncStore().claim(request_id, "test"))
        connection = Mock()
        with (
            patch("services.pdb_ref_sync._connect_vm04", return_value=connection),
            patch(
                "services.pdb_ref_sync._run_remote",
                side_effect=[
                    "ROWS=2182145\nCOLUMNS=17\n",
                    '{"document_count": 2182145, "retriever_version": "pdb-bm25-vm04-v1"}\n',
                ],
            ),
            patch(
                "services.pdb_ref_sync._download_parquet",
                return_value=(144747875, 144747875),
            ),
        ):
            run_pdb_ref_sync(request_id)

        job = PdbRefSyncStore().get()
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["row_count"], 2182145)
        self.assertEqual(job["column_count"], 17)
        self.assertEqual(job["document_count"], 2182145)
        self.assertEqual(job["retriever_version"], "pdb-bm25-vm04-v1")
        connection.close.assert_called_once()

    def test_local_file_status_uses_ref_pdb_dump_name(self):
        target = self.data_dir / "ref_pdb_dump.parquet"
        target.write_bytes(b"PAR1fixturePAR1")

        status = pdb_ref_status()

        self.assertTrue(status["file"]["available"])
        self.assertEqual(status["file"]["name"], "ref_pdb_dump.parquet")
        self.assertEqual(status["file"]["size_bytes"], target.stat().st_size)


if __name__ == "__main__":
    unittest.main()
