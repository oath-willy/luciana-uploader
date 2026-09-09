import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.mc_code import legacy_router, router
from services.mc_code_local_store import McCodeSnapshotStore, publish_snapshot, snapshot_path


class McCodeLocalApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        data_dir = Path(self.temporary.name)
        self.environment_patch = patch.dict(
            os.environ,
            {
                "MC_CODE_LOCAL_DATA_DIR": str(data_dir),
                "MC_CODE_RUNTIME_DB": str(data_dir / "runtime.sqlite3"),
                "MC_CODE_SNAPSHOT_TOKEN": "snapshot-test-token",
                "BS25AI_MOCK_MODE": "true",
                "BS25_WORKER_URL": "http://vm04.test:8094",
                "BS25_WORKER_TOKEN": "worker-test-token",
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
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.include_router(legacy_router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.environment_patch.stop()
        self.temporary.cleanup()

    def test_search_and_select_all_use_local_snapshot(self):
        search = self.client.post(
            "/api/mc-code/search",
            json={"environment": "dev", "company": "HERAEUS", "page_size": 25},
        )
        eligible = self.client.post(
            "/api/mc-code/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )

        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["total"], 3)
        self.assertEqual(eligible.json()["total"], 1)

        companies = self.client.get("/api/mc-code/companies?environment=dev")
        config = self.client.get("/api/mc-code/config")
        self.assertEqual([item["value"] for item in companies.json()], ["HERAEUS"])
        self.assertEqual(config.json()["data_source"], "local_snapshot")
        self.assertTrue(config.json()["pdb_available"]["dev"])
        self.assertTrue(config.json()["bs25ai_mock_mode"])

    def test_legacy_urls_keep_query_and_post_body(self):
        companies = self.client.get("/api/codex/companies?environment=dev")
        self.assertEqual(companies.status_code, 200)
        self.assertEqual([item["value"] for item in companies.json()], ["HERAEUS"])
        search = self.client.post(
            "/api/codex/search",
            json={"environment": "dev", "company": "HERAEUS", "page_size": 25},
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["total"], 3)

    def test_legacy_snapshot_settings_and_header_remain_usable(self):
        snapshot_bytes = snapshot_path("dev").read_bytes()
        settings = {key: value for key, value in os.environ.items() if not key.startswith("MC_CODE_")}
        settings.update({
            "CODEX_LOCAL_DATA_DIR": self.temporary.name,
            "CODEX_RUNTIME_DB": str(Path(self.temporary.name) / "runtime.sqlite3"),
            "CODEX_SNAPSHOT_TOKEN": "legacy-test-token",
        })
        with patch.dict(os.environ, settings, clear=True):
            published = self.client.put(
                "/api/codex/snapshot-file?environment=dev",
                content=snapshot_bytes,
                headers={"X-Codex-Snapshot-Token": "legacy-test-token"},
            )
            denied = self.client.put(
                "/api/mc-code/snapshot-file?environment=dev",
                content=snapshot_bytes,
                headers={"X-Codex-Snapshot-Token": "wrong-token"},
            )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["rows"], 3)
        self.assertEqual(denied.status_code, 401)

    def test_snapshot_selection_is_not_eligible_and_can_be_cleared_locally(self):
        before = self.client.post(
            "/api/mc-code/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        cleared = self.client.post(
            "/api/mc-code/bs25/select",
            json={
                "environment": "dev",
                "company": "HERAEUS",
                "item_code": "A3",
                "clear": True,
                "selection_request_id": "selection-request-0003",
            },
        )
        after = self.client.post(
            "/api/mc-code/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )

        self.assertEqual(before.json()["total"], 1)
        self.assertTrue(cleared.json()["selected"])
        self.assertEqual(after.json()["total"], 2)

    def test_prebuilt_snapshot_upload_is_authenticated_and_validated(self):
        snapshot_bytes = snapshot_path("dev").read_bytes()
        unauthorized = self.client.put(
            "/api/mc-code/snapshot-file?environment=dev",
            content=snapshot_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        published = self.client.put(
            "/api/mc-code/snapshot-file?environment=dev",
            content=snapshot_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "X-MC-Code-Snapshot-Token": "snapshot-test-token",
            },
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["rows"], 3)
        self.assertEqual(published.json()["master_codes"], 1)

    def test_submit_ai_and_local_selection_contract(self):
        selection = self.client.post(
            "/api/mc-code/bs25/select",
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
            "/api/mc-code/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        self.assertEqual(no_longer_eligible.json()["total"], 0)

        cleared = self.client.post(
            "/api/mc-code/bs25/select",
            json={
                "environment": "dev",
                "company": "HERAEUS",
                "item_code": "A1",
                "clear": True,
                "selection_request_id": "selection-request-0002",
            },
        )
        eligible_again = self.client.post(
            "/api/mc-code/bs25ai/eligible",
            json={"environment": "dev", "company": "HERAEUS"},
        )
        self.assertTrue(cleared.json()["selected"])
        self.assertEqual(eligible_again.json()["total"], 1)

        with patch("api.mc_code.run_bs25ai_job") as runner:
            response = self.client.post(
                "/api/mc-code/bs25ai",
                json={"environment": "dev", "company": "HERAEUS", "item_codes": ["A1"]},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted_item_codes"], ["A1"])
        runner.assert_called_once()

    def test_bs25_is_delegated_to_vm04_worker(self):
        with patch("api.mc_code.run_bs25_batch") as runner:
            response = self.client.post(
                "/api/mc-code/bs25",
                json={"environment": "dev", "company": "HERAEUS", "item_codes": ["A2"]},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["accepted_item_codes"], ["A2"])
        runner.assert_called_once_with("dev", "HERAEUS", ["A2"])


if __name__ == "__main__":
    unittest.main()
