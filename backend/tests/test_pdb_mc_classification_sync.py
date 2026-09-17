import os
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pdb_settings import router
from services.pdb_mc_classification_sync import (
    _publish_to_vm, classification_job_store, classification_status, run_classification_sync,
)


class McClassificationSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = self.root / "key.pem"
        self.key.write_text("fixture", encoding="utf-8")
        self.parquet = self.root / "source.parquet"
        pq.write_table(pa.table({"item_code": ["1", "2"], "master_code": ["01_02_03", "02_03_04"]}), self.parquet)
        self.env = patch.dict(os.environ, {
            "MC_CODE_LOCAL_DATA_DIR": str(self.root),
            "PDB_REF_SSH_PRIVATE_KEY_PATH": str(self.key),
            "PDB_MC_CLASSIFICATION_LOCAL_PATH": str(self.root / "pdb_mc_classification.parquet"),
            "PDB_MC_CLASSIFICATION_STATUS_DB": str(self.root / "classification-status.sqlite3"),
            "PDB_MC_CLASSIFICATION_REMOTE_PATH": "/vm/pdb/pdb_mc_classification.parquet",
        })
        self.env.start()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def blob(self):
        blob = Mock()
        blob.__enter__ = Mock(return_value=blob)
        blob.__exit__ = Mock(return_value=False)
        blob.get_blob_properties.return_value = Mock(size=self.parquet.stat().st_size, etag='"etag"')
        blob.download_blob.return_value.readinto.side_effect = lambda stream: stream.write(self.parquet.read_bytes())
        return blob

    def test_refresh_downloads_validates_and_publishes_both_copies(self):
        connection = Mock()
        published = []
        with (
            patch("services.pdb_mc_classification_sync._blob_client", return_value=self.blob()),
            patch("services.pdb_mc_classification_sync.connect_vm04", return_value=connection),
            patch("services.pdb_mc_classification_sync._publish_to_vm",
                  side_effect=lambda _client, path, remote: published.append((path.read_bytes(), remote))),
        ):
            response = self.client.post("/api/pdb/settings/mc-classification/refresh")

        self.assertEqual(response.status_code, 202)
        status = classification_status()
        self.assertEqual(status["job"]["status"], "completed")
        self.assertEqual(status["job"]["row_count"], 2)
        self.assertEqual(status["job"]["column_count"], 2)
        self.assertEqual(status["copies"], {"backend": True, "vm04": True})
        self.assertEqual(status["file"]["name"], "pdb_mc_classification.parquet")
        self.assertEqual(Path(os.environ["PDB_MC_CLASSIFICATION_LOCAL_PATH"]).read_bytes(), self.parquet.read_bytes())
        self.assertEqual(published, [(self.parquet.read_bytes(), "/vm/pdb/pdb_mc_classification.parquet")])
        connection.close.assert_called_once()

    def test_failed_sync_retains_previous_backend_file(self):
        target = Path(os.environ["PDB_MC_CLASSIFICATION_LOCAL_PATH"])
        target.write_bytes(b"previous")
        classification_job_store().claim("failed", "test")
        with patch("services.pdb_mc_classification_sync._blob_client", side_effect=RuntimeError("offline")):
            run_classification_sync("failed")
        self.assertEqual(target.read_bytes(), b"previous")
        self.assertEqual(classification_status()["job"]["status"], "failed")
        self.assertEqual(classification_status()["copies"], {"backend": False, "vm04": False})

    def test_vm_publication_uses_complete_temporary_file_and_atomic_move(self):
        source = self.root / "upload.parquet"
        source.write_bytes(b"PAR1fixturePAR1")
        remote_files = {}

        class RemoteFile(io.BytesIO):
            def __init__(self, name):
                super().__init__()
                self.name = name

            def close(inner_self):
                remote_files[inner_self.name] = inner_self.getvalue()
                super().close()

        sftp = Mock()
        sftp.file.side_effect = lambda name, _mode: RemoteFile(name)
        sftp.stat.side_effect = lambda name: Mock(st_size=len(remote_files[name]))
        connection = Mock()
        connection.open_sftp.return_value = sftp
        with patch("services.pdb_mc_classification_sync._run_remote") as move:
            _publish_to_vm(connection, source, "/vm/pdb/pdb_mc_classification.parquet")
        temporary = next(iter(remote_files))
        self.assertEqual(remote_files[temporary], source.read_bytes())
        command = move.call_args.args[1]
        self.assertIn(temporary, command)
        self.assertTrue(command.endswith(" /vm/pdb/pdb_mc_classification.parquet"))

    def test_second_refresh_is_rejected_while_active(self):
        classification_job_store().claim("active", "test")
        self.assertEqual(self.client.post("/api/pdb/settings/mc-classification/refresh").status_code, 409)


if __name__ == "__main__":
    unittest.main()
