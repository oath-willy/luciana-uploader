import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from services.codex_bs25ai import (
    Bs25AiWorkerError,
    MockBs25AiWorkerClient,
    run_bs25ai_job,
    run_bs25ai_xhigh,
)
from services.codex_local_store import (
    CodexSnapshotStore,
    RuntimeStore,
    SnapshotValidationError,
    publish_snapshot,
)


class _FakeWorker:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def review(self, **payload):
        self.calls.append(payload)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _proposal(rank, code, *, exact=False, manufacturer="KULZER"):
    return {
        "identity_rank": rank,
        "identity_score": 1 / rank,
        "exact_match": exact,
        "pdb_ref": f"PDB-{rank}",
        "pdb_description": f"HeraCeram candidate {rank}",
        "master_code": code,
        "manufacturer": manufacturer,
    }


class CodexBs25AiFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.environment_patch = patch.dict(
            os.environ,
            {
                "CODEX_LOCAL_DATA_DIR": str(self.data_dir),
                "CODEX_RUNTIME_DB": str(self.data_dir / "runtime.sqlite3"),
            },
        )
        self.environment_patch.start()
        self.rows = [
            self._row("EXACT", [_proposal(1, "38_02_02", exact=True), _proposal(2, "38_02_02"), _proposal(3, "38_02_02")]),
            self._row("COHERENT", [_proposal(1, "38_02_02"), _proposal(2, "38_02_03"), _proposal(3, "38_02_04")]),
            self._row("TOWEL", [_proposal(1, "09_05_03", manufacturer="BK"), _proposal(2, "91_03_00", manufacturer="CREATION"), _proposal(3, "38_09_99", manufacturer="GC")]),
            self._row("ERROR", [_proposal(1, "38_02_02"), _proposal(2, "38_02_03"), _proposal(3, "38_02_04")]),
        ]
        master_codes = [
            {"master_code": code, "components": {"mc_lvl1_code": code[:2]}}
            for code in {"38_02_02", "38_02_03", "38_02_04", "09_05_03", "91_03_00", "38_09_99", "77_01_01"}
        ]
        publish_snapshot(
            "dev",
            "fixture-v1",
            "2026-09-02T00:00:00Z",
            [{"company": "HERAEUS", "full_view_available": True, "extra_columns": []}],
            self.rows,
            master_codes,
        )

    def tearDown(self):
        self.environment_patch.stop()
        self.temporary.cleanup()

    @staticmethod
    def _row(item_code, proposals):
        return {
            "company": "HERAEUS",
            "item_code": item_code,
            "company_item_code": f"HERAEUS|{item_code}",
            "description": item_code,
            "bs25_status": "completed",
            "bs25_proposal_1": proposals[0],
            "bs25_proposal_2": proposals[1],
            "bs25_proposal_3": proposals[2],
            "details": {},
        }

    def _create_job(self, item_code):
        created = RuntimeStore().create_job(
            "dev", "HERAEUS", item_code, f"request-{item_code}", "test"
        )
        self.assertTrue(created)

    def test_exact_match_completes_without_llm(self):
        self._create_job("EXACT")
        worker = _FakeWorker([])

        run_bs25ai_job("dev", "HERAEUS", "EXACT", worker=worker)

        job = RuntimeStore().get_job("dev", "HERAEUS", "EXACT")
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["stage"], "bs25_exact")
        self.assertEqual(job["result"]["selected_candidate_rank"], 1)
        self.assertEqual(worker.calls, [])

    def test_coherent_fuzzy_always_runs_sol_low(self):
        self._create_job("COHERENT")
        worker = _FakeWorker(
            [{
                "thread_id": "thread-low",
                "result": {
                    "decision": "match",
                    "selected_candidate_rank": 1,
                    "proposed_master_code": "38_02_02",
                    "confidence": "medium",
                    "rationale": "candidate supported",
                    "components": None,
                    "evidence": [],
                },
            }]
        )

        run_bs25ai_job("dev", "HERAEUS", "COHERENT", worker=worker)

        job = RuntimeStore().get_job("dev", "HERAEUS", "COHERENT")
        self.assertEqual(worker.calls[0]["mode"], "low")
        self.assertTrue(job["taxonomy_coherent"])
        self.assertIn("tassonomicamente coerenti", job["flag"])

    def test_heterogeneous_low_can_escalate_to_xhigh_and_leave_top_three(self):
        self._create_job("TOWEL")
        low = _FakeWorker(
            [{
                "thread_id": "thread-towel",
                "result": {
                    "decision": "ambiguous",
                    "selected_candidate_rank": None,
                    "proposed_master_code": None,
                    "confidence": "low",
                    "rationale": "insufficient internal evidence",
                    "components": None,
                    "evidence": [],
                },
            }]
        )
        run_bs25ai_job("dev", "HERAEUS", "TOWEL", worker=low)
        xhigh = _FakeWorker(
            [{
                "thread_id": "thread-towel",
                "result": {
                    "decision": "match",
                    "selected_candidate_rank": None,
                    "proposed_master_code": "77_01_01",
                    "confidence": "high",
                    "rationale": "official source",
                    "components": {"manufacturer": "Kulzer"},
                    "evidence": [{"url": "https://example.test", "title": "Official", "basis": "exact ref"}],
                },
            }]
        )

        run_bs25ai_xhigh("dev", "HERAEUS", "TOWEL", worker=xhigh)

        job = RuntimeStore().get_job("dev", "HERAEUS", "TOWEL")
        self.assertEqual(job["stage"], "sol_xhigh_web")
        self.assertEqual(job["result"]["proposed_master_code"], "77_01_01")
        self.assertEqual(xhigh.calls[0]["thread_id"], "thread-towel")
        self.assertTrue(xhigh.calls[0]["canonical_master_codes"])

    def test_llm_error_does_not_overwrite_operator_selection(self):
        runtime = RuntimeStore()
        runtime.save_selection(
            "dev", "HERAEUS", "ERROR", "proposal", 3, "38_02_04", "selection-request-1", "test"
        )
        self._create_job("ERROR")

        run_bs25ai_job(
            "dev",
            "HERAEUS",
            "ERROR",
            worker=_FakeWorker([Bs25AiWorkerError("simulated failure")]),
        )

        job = runtime.get_job("dev", "HERAEUS", "ERROR")
        rows = CodexSnapshotStore("dev").search("HERAEUS", "light", 0, 25, "ERROR", {})["rows"]
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["result"])
        self.assertEqual(rows[0]["bs25_selected_master_code"], "38_02_04")

    def test_mock_worker_marks_result_and_does_not_require_vm04(self):
        self._create_job("COHERENT")

        run_bs25ai_job(
            "dev", "HERAEUS", "COHERENT", worker=MockBs25AiWorkerClient()
        )

        job = RuntimeStore().get_job("dev", "HERAEUS", "COHERENT")
        self.assertEqual(job["status"], "completed")
        self.assertTrue(job["result"]["simulated"])
        self.assertTrue(job["thread_id"].startswith("mock-"))

    def test_snapshot_refresh_preserves_runtime_selection(self):
        runtime = RuntimeStore()
        runtime.save_selection(
            "dev", "HERAEUS", "EXACT", "proposal", 1, "38_02_02", "selection-refresh", "test"
        )
        refreshed_rows = [dict(row) for row in self.rows]
        refreshed_rows[0] = {**refreshed_rows[0], "description": "updated description"}

        publish_snapshot(
            "dev",
            "fixture-v2",
            "2026-09-03T00:00:00Z",
            [{"company": "HERAEUS", "full_view_available": True, "extra_columns": []}],
            refreshed_rows,
            [{"master_code": "38_02_02", "components": {}}],
        )

        row = CodexSnapshotStore("dev").search("HERAEUS", "light", 0, 25, "EXACT", {})["rows"][0]
        self.assertEqual(row["description"], "updated description")
        self.assertEqual(row["bs25_selected_master_code"], "38_02_02")

    def test_invalid_snapshot_does_not_replace_current_snapshot(self):
        with self.assertRaises(SnapshotValidationError):
            publish_snapshot(
                "dev",
                "invalid",
                "2026-09-03T00:00:00Z",
                [],
                [self.rows[0]],
                [{"master_code": "38_02_02", "components": {}}],
            )

        self.assertEqual(CodexSnapshotStore("dev").metadata()["snapshot_id"], "fixture-v1")

    def test_runtime_initialization_is_safe_under_parallel_reads(self):
        path = self.data_dir / "parallel-runtime.sqlite3"
        barrier = threading.Barrier(8)
        errors = []

        def initialize():
            try:
                barrier.wait()
                RuntimeStore(path)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        threads = [threading.Thread(target=initialize) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
