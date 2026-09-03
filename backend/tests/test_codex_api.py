import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codex import router
from services.codex_local_retrieval import publish_pdb_snapshot
from services.codex_local_store import CodexSnapshotStore, publish_snapshot, snapshot_path


class CodexLocalApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        data_dir = Path(self.temporary.name)
        self.environment_patch = patch.dict(
            os.environ,
            {
                "CODEX_LOCAL_DATA_DIR": str(data_dir),
                "CODEX_RUNTIME_DB": str(data_dir / "runtime.sqlite3"),
                "CODEX_SNAPSHOT_TOKEN": "snapshot-test-token",
                "BS25AI_MOCK_MODE": "true",
            },
        )
        self.environment_patch.start()
        proposal = {
            "identity_rank": 1,
            "identity_score": 0.5,
            "exact_match": False,
            "pdb_ref": "PDB-1",
            "pdb_description": "fixture",
            "master_code": "38_02_02",
        }
        publish_snapshot(
            "dev",
            "api-fixture",
            "2026-09-02T00:00:00Z",
            [{"company": "HERAEUS", "full_view_available": True, "extra_columns": []}],
            [
                {
                    "company": "HERAEUS",
                    "item_code": "A1",
                    "company_item_code": "HERAEUS|A1",
                    "description": "fixture",
                    "bs25_status": "completed",
                    "bs25_proposal_1": {**proposal, "identity_rank": 1},
                    "bs25_proposal_2": {**proposal, "identity_rank": 2},
                    "bs25_proposal_3": {**proposal, "identity_rank": 3},
                    "details": {},
                },
                {
                    "company": "HERAEUS",
                    "item_code": "A2",
                    "company_item_code": "HERAEUS|A2",
                    "description": "HeraCeram cre active indication",
                    "details": {},
                },
                {
                    "company": "HERAEUS",
                    "item_code": "A3",
                    "company_item_code": "HERAEUS|A3",
                    "description": "already selected fixture",
                    "bs25_status": "completed",
                    "bs25_proposal_1": {**proposal, "identity_rank": 1},
                    "bs25_proposal_2": {**proposal, "identity_rank": 2},
                    "bs25_proposal_3": {**proposal, "identity_rank": 3},
                    "bs25_selected_proposal_rank": 1,
                    "bs25_selected_master_code": "38_02_02",
                    "bs25_selection_status": "completed",
                    "details": {},
                },
            ],
            [{"master_code": "38_02_02", "components": {}}],
        )
        publish_pdb_snapshot(
            "dev",
            "pdb-fixture",
            "2026-09-02T00:00:00Z",
            [
                {"company_item_code": "PDB-1", "item_description_cleaned": "HeraCeram cre active indication", "master_code": "38_02_02"},
                {"company_item_code": "PDB-2", "item_description_cleaned": "HeraCeram cre active color", "master_code": "38_02_02"},
                {"company_item_code": "PDB-3", "item_description_cleaned": "HeraCeram indication set", "master_code": "38_02_02"},
                {"company_item_code": "PDB-4", "item_description_cleaned": "unrelated dental product", "master_code": "38_02_02"},
            ],
        )
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.environment_patch.stop()
        self.temporary.cleanup()

    def test_search_and_select_all_use_local_snapshot(self):
        search = self.client.post(
            "/api/codex/search",
            json={"environment": "dev", "company": "HERAEUS", "page_size": 25},
        )
        eligible = self.client.post(
            "/api/codex/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )

        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["total"], 3)
        self.assertEqual(eligible.json()["total"], 1)

        companies = self.client.get("/api/codex/companies?environment=dev")
        config = self.client.get("/api/codex/config")
        self.assertEqual([item["value"] for item in companies.json()], ["HERAEUS"])
        self.assertEqual(config.json()["data_source"], "local_snapshot")
        self.assertTrue(config.json()["pdb_available"]["dev"])
        self.assertTrue(config.json()["bs25ai_mock_mode"])

    def test_snapshot_selection_is_not_eligible_and_can_be_cleared_locally(self):
        before = self.client.post(
            "/api/codex/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        cleared = self.client.post(
            "/api/codex/bs25/select",
            json={
                "environment": "dev",
                "company": "HERAEUS",
                "item_code": "A3",
                "clear": True,
                "selection_request_id": "selection-request-0003",
            },
        )
        after = self.client.post(
            "/api/codex/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )

        self.assertEqual(before.json()["total"], 1)
        self.assertTrue(cleared.json()["selected"])
        self.assertEqual(after.json()["total"], 2)

    def test_prebuilt_snapshot_upload_is_authenticated_and_validated(self):
        snapshot_bytes = snapshot_path("dev").read_bytes()
        unauthorized = self.client.put(
            "/api/codex/snapshot-file?environment=dev",
            content=snapshot_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        published = self.client.put(
            "/api/codex/snapshot-file?environment=dev",
            content=snapshot_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Codex-Snapshot-Token": "snapshot-test-token",
            },
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["rows"], 3)
        self.assertEqual(published.json()["master_codes"], 1)

    def test_submit_ai_and_local_selection_contract(self):
        selection = self.client.post(
            "/api/codex/bs25/select",
            json={
                "environment": "dev",
                "company": "HERAEUS",
                "item_code": "A1",
                "proposal_rank": 1,
                "selection_request_id": "selection-request-0001",
            },
        )

        self.assertTrue(selection.json()["selected"])

        no_longer_eligible = self.client.post(
            "/api/codex/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        self.assertEqual(no_longer_eligible.json()["total"], 0)

        cleared = self.client.post(
            "/api/codex/bs25/select",
            json={
                "environment": "dev",
                "company": "HERAEUS",
                "item_code": "A1",
                "clear": True,
                "selection_request_id": "selection-request-0002",
            },
        )
        eligible_again = self.client.post(
            "/api/codex/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        self.assertTrue(cleared.json()["selected"])
        self.assertEqual(eligible_again.json()["total"], 1)

        with patch("api.codex.run_bs25ai_job") as runner:
            response = self.client.post(
                "/api/codex/bs25ai",
                json={"environment": "dev", "company": "HERAEUS", "item_codes": ["A1"]},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted_item_codes"], ["A1"])
        runner.assert_called_once()

    def test_bs25_runs_against_local_pdb(self):
        response = self.client.post(
            "/api/codex/bs25",
            json={"environment": "dev", "company": "HERAEUS", "item_codes": ["A2"]},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted_item_codes"], ["A2"])
        row = CodexSnapshotStore("dev").get_items("HERAEUS", ["A2"])[0]
        self.assertEqual(row["bs25_status"], "completed")
        self.assertEqual(row["bs25_proposal_1"]["pdb_ref"], "PDB-1")
        self.assertEqual(row["bs25_proposal_1"]["retriever_version"], "pdb-bm25-local-v1")


if __name__ == "__main__":
    unittest.main()
