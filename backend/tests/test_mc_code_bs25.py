import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.mc_code_bs25 import Bs25WorkerClient, run_bs25_batch
from services.mc_code_local_store import McCodeSnapshotStore, RuntimeStore, publish_snapshot


class _FakeRetriever:
    retriever_version = "pdb-bm25-vm04-v1"

    def __init__(self):
        self.items = []

    def retrieve(self, items):
        self.items = items
        proposals = [
            {
                "identity_rank": rank,
                "identity_score": 1 / rank,
                "exact_match": rank == 1,
                "pdb_ref": f"PDB-{rank}",
                "pdb_description": f"proposal {rank}",
                "master_code": "38_02_02",
                "retriever_version": self.retriever_version,
            }
            for rank in (1, 2, 3)
        ]
        return {str(items[0]["item_code"]): proposals}


class McCodeBs25WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.environment_patch = patch.dict(
            os.environ,
            {
                "MC_CODE_LOCAL_DATA_DIR": str(self.data_dir),
                "MC_CODE_RUNTIME_DB": str(self.data_dir / "runtime.sqlite3"),
            },
        )
        self.environment_patch.start()
        publish_snapshot(
            "dev",
            "bs25-worker-fixture",
            "2026-09-09T00:00:00Z",
            [{"company": "HERAEUS", "full_view_available": True}],
            [
                {
                    "company": "HERAEUS",
                    "item_code": "A2",
                    "company_item_code": "HERAEUS|A2",
                    "description": "HeraCeram cre active indication",
                    "details": {"future_parameter": "kept in extra"},
                }
            ],
            [{"master_code": "38_02_02", "components": {}}],
        )
        RuntimeStore().create_bs25_job(
            "dev", "HERAEUS", "A2", "request-bs25-a2", "test"
        )

    def tearDown(self):
        self.environment_patch.stop()
        self.temporary.cleanup()

    def test_result_is_persisted_with_existing_runtime_flow(self):
        retriever = _FakeRetriever()
        run_bs25_batch("dev", "HERAEUS", ["A2"], retriever=retriever)

        row = McCodeSnapshotStore("dev").get_items("HERAEUS", ["A2"])[0]
        self.assertEqual(retriever.items[0]["company"], "HERAEUS")
        self.assertEqual(row["bs25_status"], "completed")
        self.assertEqual(row["bs25_proposal_1"]["pdb_ref"], "PDB-1")
        self.assertEqual(
            row["bs25_proposal_1"]["retriever_version"], "pdb-bm25-vm04-v1"
        )

    @patch("services.mc_code_bs25.requests.post")
    def test_client_sends_extensible_contract_and_validates_top_three(self, post: Mock):
        post.return_value.ok = True
        post.return_value.json.return_value = {
            "retriever_version": "pdb-bm25-vm04-v1",
            "results": [
                {
                    "company": "HERAEUS",
                    "item_code": "A2",
                    "proposals": [
                        {
                            "identity_rank": rank,
                            "identity_score": 1 / rank,
                            "exact_match": rank == 1,
                            "pdb_ref": f"PDB-{rank}",
                            "pdb_description": f"proposal {rank}",
                            "master_code": "38_02_02",
                        }
                        for rank in (1, 2, 3)
                    ],
                }
            ],
        }
        client = Bs25WorkerClient("http://vm04.test:8094", "token")

        result = client.retrieve(
            [
                {
                    "company": "HERAEUS",
                    "item_code": "A2",
                    "description": "description",
                    "future_parameter": "value",
                }
            ]
        )

        sent = post.call_args.kwargs["json"]["items"][0]
        self.assertEqual(sent["company"], "HERAEUS")
        self.assertEqual(sent["item_code"], "A2")
        self.assertEqual(sent["description"], "description")
        self.assertEqual(sent["extra"], {"future_parameter": "value"})
        self.assertEqual(len(result["A2"]), 3)


if __name__ == "__main__":
    unittest.main()
