import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.mc_code import router
from services.mc_code_local_store import McCodeSnapshotStore, RuntimeStore, publish_snapshot
from services.mc_code_pac_ai import PacAiStore, classification, sync_pac_ai, worker_item


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MC_CODE_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MC_CODE_RUNTIME_DB", str(tmp_path / "runtime.sqlite3"))
    monkeypatch.setenv("PDB_MC_CLASSIFICATION_LOCAL_PATH", str(tmp_path / "classification.parquet"))
    monkeypatch.setenv("PAC_AI_WORKER_URL", "http://vm.test")
    monkeypatch.setenv("PAC_AI_WORKER_TOKEN", "token")
    pq.write_table(pa.Table.from_pylist([
        {"master_code": "38_02_03", "family": "CERAMICS", "subfamily": "TOOLS", "product_group": "BRUSHES", "mc_desc": "Pennelli"}
    ]), tmp_path / "classification.parquet")
    items = [{"company": "DEALER", "item_code": "A1", "company_item_code": "DEALER|A1", "description": "ceramic brush",
              "details": {"brand": "BRAND", "item_extra_descriptions": {"manufacturer": "MAKER"}}}]
    # Snapshot MC list intentionally differs: PAC-AI must validate against the new classification file.
    publish_snapshot("dev", "fixture", "2026-09-17", [{"company": "DEALER", "extra_columns": []}], items,
                     [{"master_code": "38_02_02", "components": {}}])
    app = FastAPI()
    app.include_router(router, prefix="/api")
    monkeypatch.setattr("api.mc_code.sync_pac_ai", lambda *args: None)
    return TestClient(app)


def result(version, **kwargs):
    return {"taxonomy_version": version, "decision": "match", "master_code": "38_02_03", "initial_master_code": "38_02_03",
            "confidence": "high", "rationale": "Pennello", "evidence": [],
            "classification": {"family": "untrusted label"}, **kwargs}


class Worker:
    def __init__(self): self.jobs = {}; self.submissions = []
    def status(self, ids): return [self.jobs[i] for i in ids if i in self.jobs]
    def submit(self, jobs):
        self.submissions.extend(jobs)
        for job in jobs:
            self.jobs[job["request_id"]] = {"request_id": job["request_id"], "status": "queued", "stage": "queued"}
        return self.status([j["request_id"] for j in jobs])


def test_independent_of_bs25_idempotent_and_recovers_dispatch_after_restart(setup):
    client = setup
    payload = {"company": "DEALER", "item_codes": ["A1"]}
    assert client.post("/api/mc-code/pac-ai", json=payload).json()["accepted_item_codes"] == ["A1"]
    assert client.post("/api/mc-code/pac-ai", json=payload).json()["locked_item_codes"] == ["A1"]
    worker = Worker()
    assert sync_pac_ai("dev", "DEALER", worker)["active"]
    request = worker.submissions[0]
    sync_pac_ai("dev", "dealer", worker)
    assert len(worker.submissions) == 1
    worker.jobs[request["request_id"]].update(status="completed", stage="completed", result=result(request["taxonomy_version"]))
    assert not sync_pac_ai("dev", "DEALER", worker)["active"]
    row = McCodeSnapshotStore("dev").get_items("DEALER", ["A1"])[0]
    assert row["pac_ai_result"]["master_code"] == "38_02_03"
    assert row["pac_ai_result"]["classification"]["family"] == "CERAMICS"
    assert not row["bs25_status"] and not row.get("bs25_selected_master_code")
    # A late polling response cannot regress a completed job to queued.
    PacAiStore().update(request["request_id"], status="queued")
    assert McCodeSnapshotStore("dev").get_items("DEALER", ["A1"])[0]["pac_ai_status"] == "completed"


@pytest.mark.parametrize("bad_result", [{"master_code": "99_99_99"}, {"taxonomy_version": "old"}, {"evidence": [{"pdb_ref": "fake", "master_code": "99_99_99"}]}])
def test_bad_results_fail_and_retry_uses_new_id_without_touching_selection(setup, bad_result):
    RuntimeStore().save_selection("dev", "DEALER", "A1", "proposal", 1, "38_02_02", "selection-id-0001", "test")
    setup.post("/api/mc-code/pac-ai", json={"company": "DEALER", "item_codes": ["A1"]})
    worker = Worker(); sync_pac_ai("dev", "DEALER", worker)
    request = worker.submissions[0]
    worker.jobs[request["request_id"]].update(status="completed", stage="completed", result=result(request["taxonomy_version"], **bad_result))
    sync_pac_ai("dev", "DEALER", worker)
    row = McCodeSnapshotStore("dev").get_items("DEALER", ["A1"])[0]
    assert row["pac_ai_status"] == "failed" and row["pac_ai_result"] is None
    assert row["bs25_selected_master_code"] == "38_02_02"
    assert setup.post("/api/mc-code/pac-ai", json={"company": "DEALER", "item_codes": ["A1"]}).json()["accepted_item_codes"] == ["A1"]
    assert PacAiStore().active("dev", "DEALER")[0]["request_id"] != request["request_id"]


def test_source_input_does_not_include_other_classifiers_or_saved_codes(setup):
    item = McCodeSnapshotStore("dev").get_items("DEALER", ["A1"])[0]
    item.update(pac_ai_result={"master_code": "wrong"}, aibs25_result={"proposed_master_code": "wrong"}, bs25_proposal_1={"master_code": "wrong"})
    payload = worker_item(item)
    assert "wrong" not in json.dumps(payload)
    assert payload["extra"]["item_extra_descriptions"]["manufacturer"] == "MAKER"


def test_worker_outage_preserves_job_for_reconnection(setup):
    setup.post("/api/mc-code/pac-ai", json={"company": "DEALER", "item_codes": ["A1"]})
    class Offline:
        def status(self, ids): raise ConnectionError("offline")
    status = sync_pac_ai("dev", "DEALER", Offline())
    assert status["active"] and "offline" in status["error_message"]
    assert len(PacAiStore().active("dev", "DEALER")) == 1


def test_rejects_missing_items_and_oversized_batches(setup):
    assert setup.post("/api/mc-code/pac-ai", json={"company": "DEALER", "item_codes": ["MISSING"]}).status_code == 404
    assert setup.post("/api/mc-code/pac-ai", json={"company": "DEALER", "item_codes": [str(i) for i in range(101)]}).status_code == 400
