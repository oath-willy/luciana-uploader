import base64
import io
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from api.fast_track import require_fast_track_user, router
from services import fast_track as service
from services import fast_track_remote as remote


class FastTrackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"FAST_TRACK_LOCAL_DIR": str(self.root), "FAST_TRACK_SOURCE_USER": "wilson_sgroi",
                                          "FAST_TRACK_ENABLED": "true", "FAST_TRACK_JOB_TIMEOUT_SECONDS": "3600"})
        self.env.start()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[require_fast_track_user] = lambda: "test@key-stone.it"
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def complete(self, kind, meta):
        store = service.Store()
        identifier = store.claim(kind, "all", "test")
        store.complete(identifier, meta)
        return identifier

    def sources(self):
        source = "a" * 32
        folder = self.root / "sources" / source
        files = {}
        for name in service.FOLDERS.values():
            files.update({f"{name}/index.html": b'<meta http-equiv="refresh" content="0; url=Page%20Name.html">',
                          f"{name}/Page Name.html": b"<html>dashboard</html>", f"{name}/support.js": b"runtime",
                          f"{name}/link_runs.R": b"dashboard_contract <- 3L"})
        files["gold_monitoring_dashboard/collection_status.R"] = b"status"
        for name, value in files.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        self.complete("sources", {"sources": {"revision": source, "source_user": "wilson_sgroi", "updated_at": "previous",
                    "dashboards": {key: {"available": True, "updated_at": "previous"} for key in service.FOLDERS}}})
        return source, files

    def test_claim_is_shared_across_source_and_data_jobs(self):
        store = service.Store()
        first = store.claim("sources", "all", "test")
        self.assertIsNotNone(first)
        self.assertIsNone(service.Store().claim("data", "all", "other"))
        store.update(first, status="failed")
        self.assertIsNotNone(service.Store().claim("data", "all", "other"))

    def test_host_identity_is_verified_before_connecting(self):
        key = Mock()
        key.asbytes.return_value = b"verified-key"
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(b"verified-key").digest()).decode().rstrip("=")
        with patch.dict(os.environ, {"FAST_TRACK_SSH_HOST_KEY_SHA256": fingerprint}):
            service.PinnedHostKeyPolicy().missing_host_key(Mock(), "vm", key)
            key.asbytes.return_value = b"unexpected-key"
            with self.assertRaises(service.paramiko.SSHException):
                service.PinnedHostKeyPolicy().missing_host_key(Mock(), "vm", key)

    def test_failed_data_job_preserves_publication_and_last_success(self):
        self.sources()
        previous = {"revision": "b" * 32, "updated_at": "last-success", "source_user": "wilson_sgroi"}
        self.complete("data", {"publication": previous})
        job = service.Store().claim("data", "all", "test")
        with patch.object(service, "_open_remote", side_effect=RuntimeError("R failed")):
            service.run_job(job, "data", "all")
        self.assertEqual(service.Store().meta("publication"), previous)
        self.assertEqual(service.status()["data"]["updated_at"], "last-success")
        self.assertEqual(service.Store().job()["status"], "failed")

    def test_source_download_validation_failure_preserves_previous_sources(self):
        self.sources()
        before = service.Store().meta("sources")
        job = service.Store().claim("sources", "all", "test")
        connection, output = Mock(), Mock()
        output.read.return_value = json.dumps({"files": {"../../escaped.html": base64.b64encode(b"bad").decode()}}).encode()
        output.channel.recv_exit_status.return_value = 0
        with patch.object(service, "_open_remote", return_value=(connection, output, io.BytesIO())):
            service.run_job(job, "sources", "all")
        self.assertEqual(service.Store().meta("sources"), before)
        self.assertFalse((self.root / "sources" / job).exists())
        connection.close.assert_called_once()

    def test_single_source_refresh_tracks_shared_assets_without_changing_other_retrieval_date(self):
        _, files = self.sources()
        selected = {name: base64.b64encode(content).decode() for name, content in files.items()
                    if name.startswith("gold_monitoring_dashboard/")}
        selected["assets/logo.svg"] = base64.b64encode(b"updated logo").decode()
        output = Mock()
        output.read.return_value = json.dumps({"files": selected}).encode()
        output.channel.recv_exit_status.return_value = 0
        job = service.Store().claim("sources", "gold", "test")
        with patch.object(service, "_open_remote", return_value=(Mock(), output, io.BytesIO())):
            service.run_job(job, "sources", "gold")
        dashboards = service.Store().meta("sources")["dashboards"]
        self.assertNotEqual(dashboards["gold"]["updated_at"], "previous")
        self.assertEqual(dashboards["forecast"]["updated_at"], "previous")
        self.assertTrue(dashboards["forecast"]["sha256"])

    def test_data_scripts_publish_timestamps_and_immutable_revision(self):
        source, _ = self.sources()
        events = [{"stage": "gold_links"}, {"result": "gold_links", "message": "26 clients"},
                  {"stage": "validating"}, {"completed": True, "dashboards": {"gold": {"available": True, "clients": 26}}}]
        output = Mock()
        output.__iter__ = Mock(return_value=iter(json.dumps(event).encode() for event in events))
        output.channel.recv_exit_status.return_value = 0
        job = service.Store().claim("data", "gold_links", "test")
        with patch.object(service, "_open_remote", return_value=(Mock(), output, io.BytesIO())) as execute:
            service.run_job(job, "data", "gold_links")
        published = service.Store().meta("publication")
        self.assertEqual(published["source_revision"], source)
        self.assertEqual(published["revision"], job)
        self.assertIn("gold_links", published["scripts"])
        self.assertEqual(service.Store().meta("publication:" + job), published)
        self.assertEqual(execute.call_args.args[0]["target"], "gold_links")
        self.assertTrue(service.status()["dashboards"]["gold"]["url"].endswith("gold_monitoring_dashboard/index.html"))

    def test_api_rejects_overlapping_jobs_and_requires_initial_sources(self):
        with patch.object(service, "pdb_ref_sync_configured", return_value=True), patch("api.fast_track.fast_track.run_job"):
            self.assertEqual(self.client.post("/api/fast-track/settings/data/refresh", json={"target": "all"}).status_code, 409)
            first = self.client.post("/api/fast-track/settings/sources/refresh", json={"target": "all"})
            self.assertEqual(first.status_code, 202)
            self.assertEqual(self.client.post("/api/fast-track/settings/sources/refresh", json={"target": "all"}).status_code, 409)
            self.assertEqual(self.client.post("/api/fast-track/settings/data/refresh", json={"target": "shell-command"}).status_code, 422)

    def test_private_assets_exclude_scripts_documents_models_and_traversal(self):
        source, _ = self.sources()
        revision = "b" * 32
        self.complete("data", {"publication:" + revision: {"revision": revision, "source_revision": source}})
        good = self.client.get(f"/api/fast-track/content/{revision}/gold_monitoring_dashboard/Page%20Name.html")
        self.assertEqual(good.status_code, 200)
        self.assertIn("private", good.headers["cache-control"])
        for path in ["gold_monitoring_dashboard/link_runs.R", "gold_monitoring_dashboard/DASHBOARD_SPEC.md",
                     "gold_monitoring_dashboard/data/models/model.rds", "assets/..%5C..%5Csecret.html"]:
            self.assertEqual(self.client.get(f"/api/fast-track/content/{revision}/{path}").status_code, 404, path)

    def test_remote_stream_closes_connection_when_reader_stops_early(self):
        revision = "b" * 32
        self.complete("data", {"publication:" + revision: {"revision": revision, "source_user": "wilson_sgroi"}})
        output, connection = Mock(), Mock()
        output.readline.return_value = b'{"size": 8}\n'
        output.read.return_value = b"data"
        with patch.object(service, "_open_remote", return_value=(connection, output, io.BytesIO())):
            result = service.publication_file(revision, "gold_monitoring_dashboard/data/clients.json")
        iterator = result[0]
        self.assertEqual(next(iterator), b"data")
        iterator.close()
        connection.close.assert_called_once()

    def test_incomplete_remote_stream_fails_and_closes_connection(self):
        revision = "b" * 32
        self.complete("data", {"publication:" + revision: {"revision": revision, "source_user": "wilson_sgroi"}})
        output, connection = Mock(), Mock()
        output.readline.return_value = b'{"size": 8}\n'
        output.read.side_effect = [b"data", b""]
        with patch.object(service, "_open_remote", return_value=(connection, output, io.BytesIO())):
            result = service.publication_file(revision, "gold_monitoring_dashboard/data/clients.json")
        with self.assertRaises(IOError):
            list(result[0])
        connection.close.assert_called_once()

    def test_changing_user_changes_default_root_and_requires_both_sources(self):
        self.sources()
        with patch.dict(os.environ, {"FAST_TRACK_SOURCE_USER": "lorenzo_rosso"}), patch.object(service, "pdb_ref_sync_configured", return_value=True):
            self.assertEqual(service.source_config()["source_root"], "/home/lorenzo_rosso/dtl_fast-track")
            self.assertEqual(self.client.post("/api/fast-track/settings/sources/refresh", json={"target": "gold"}).status_code, 409)

    def test_remote_read_rejects_symlink_outside_allowed_roots(self):
        releases = self.root / "remote"
        revision = "a" * 32
        data = releases / revision / "dashboard/gold_monitoring_dashboard/data"
        data.mkdir(parents=True)
        outside = self.root / "outside.json"
        outside.write_text("secret")
        try:
            (data / "clients.json").symlink_to(outside)
        except OSError:
            self.skipTest("Creating symlinks requires Windows developer mode")
        with patch.object(remote, "release_root", return_value=releases):
            with self.assertRaises(ValueError):
                remote.read_data({"revision": revision, "path": "gold_monitoring_dashboard/data/clients.json"})

    def test_cloud_auth_fails_closed_and_rejects_forged_local_access(self):
        def request(principal=None, method="GET", origin=None):
            headers = [(b"host", b"localhost")]
            if principal is not None:
                headers.append((b"x-ms-client-principal", base64.b64encode(json.dumps(principal).encode())))
            if origin:
                headers.append((b"origin", origin.encode()))
            return Request({"type": "http", "method": method, "path": "/", "headers": headers,
                            "scheme": "http", "client": ("127.0.0.1", 1234)})
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "cloud", "FAST_TRACK_AUTH_MODE": "local", "WEBSITE_AUTH_ENABLED": "true"}):
            with self.assertRaises(HTTPException) as error:
                require_fast_track_user(request())
            self.assertEqual(error.exception.status_code, 503)
        with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "cloud", "FAST_TRACK_AUTH_MODE": "linked", "WEBSITE_AUTH_ENABLED": "true"}):
            principal = {"userDetails": "wilson@key-stone.it", "userRoles": ["authenticated"], "identityProvider": "aad"}
            self.assertEqual(require_fast_track_user(request(principal)), "wilson@key-stone.it")
            with self.assertRaises(HTTPException):
                require_fast_track_user(request(principal, "POST", "https://untrusted.example"))
            principal["userRoles"] = ["anonymous"]
            with self.assertRaises(HTTPException):
                require_fast_track_user(request(principal))


if __name__ == "__main__":
    unittest.main()
