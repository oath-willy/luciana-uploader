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
from services.pdb_brands_dictionary_sync import (
    brands_dictionary_job_store,
    brands_dictionary_status,
    run_brands_dictionary_sync,
)


class BrandsDictionarySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parquet = self.root / "source.parquet"
        pq.write_table(
            pa.table({"brand_raw": ["Brand A", "Brand B"], "brand": ["A", "B"]}),
            self.parquet,
        )
        self.env = patch.dict(os.environ, {
            "MC_CODE_LOCAL_DATA_DIR": str(self.root),
            "PDB_BRANDS_DICTIONARY_LOCAL_PATH": str(
                self.root / "pdb_brands_dictionary.parquet"
            ),
            "PDB_BRANDS_DICTIONARY_STATUS_DB": str(
                self.root / "brands-dictionary-status.sqlite3"
            ),
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
        blob.get_blob_properties.return_value = Mock(
            size=self.parquet.stat().st_size,
            etag='"etag"',
        )
        blob.download_blob.return_value.readinto.side_effect = (
            lambda stream: stream.write(self.parquet.read_bytes())
        )
        return blob

    def test_refresh_downloads_validates_and_publishes_backend_copy(self):
        with patch(
            "services.pdb_brands_dictionary_sync._blob_client",
            return_value=self.blob(),
        ):
            response = self.client.post("/api/pdb/settings/brands-dictionary/refresh")

        self.assertEqual(response.status_code, 202)
        status = brands_dictionary_status()
        self.assertEqual(status["job"]["status"], "completed")
        self.assertEqual(status["job"]["row_count"], 2)
        self.assertEqual(status["job"]["column_count"], 2)
        self.assertEqual(status["copies"], {"backend": True})
        self.assertEqual(status["file"]["name"], "pdb_brands_dictionary.parquet")
        target = Path(os.environ["PDB_BRANDS_DICTIONARY_LOCAL_PATH"])
        self.assertEqual(target.read_bytes(), self.parquet.read_bytes())

    def test_failed_sync_retains_previous_backend_file(self):
        target = Path(os.environ["PDB_BRANDS_DICTIONARY_LOCAL_PATH"])
        target.write_bytes(b"previous")
        brands_dictionary_job_store().claim("failed", "test")
        with patch(
            "services.pdb_brands_dictionary_sync._blob_client",
            side_effect=RuntimeError("offline"),
        ):
            run_brands_dictionary_sync("failed")

        self.assertEqual(target.read_bytes(), b"previous")
        self.assertEqual(brands_dictionary_status()["job"]["status"], "failed")
        self.assertEqual(brands_dictionary_status()["copies"], {"backend": False})

    def test_second_refresh_is_rejected_while_active(self):
        brands_dictionary_job_store().claim("active", "test")
        response = self.client.post("/api/pdb/settings/brands-dictionary/refresh")
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
