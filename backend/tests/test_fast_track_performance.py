import io
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import paramiko

from services import fast_track as service
from services.fast_track_performance import BoundedFileCache, ExpiringKey, SSHReadPool
from tests import test_fast_track as baseline


def file_response(payload=b"data", close=None):
    return iter((payload,)), "application/octet-stream", len(payload), close or (lambda: None)


class FileCacheTests(unittest.TestCase):
    def test_concurrent_reads_share_one_download(self):
        cache = BoundedFileCache()
        entered, finish = threading.Event(), threading.Event()
        def load():
            entered.set()
            self.assertTrue(finish.wait(5))
            return file_response()
        loader = Mock(side_effect=load)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(cache.fetch, "same-file", loader) for _ in range(4)]
            self.assertTrue(entered.wait(5))
            finish.set()
            self.assertEqual([b"".join(f.result()[0]) for f in futures], [b"data"] * 4)
        loader.assert_called_once()

    def test_revisions_are_separate_and_expired_entries_are_refetched(self):
        stamp = [0]
        cache = BoundedFileCache(ttl=5, clock=lambda: stamp[0])
        load = Mock(return_value=file_response())
        cache.fetch(("user", "revision-one", "manifest"), load)
        load.return_value = file_response(b"new")
        second = cache.fetch(("user", "revision-two", "manifest"), load)
        self.assertEqual(b"".join(second[0]), b"new")
        stamp[0] = 6
        load.return_value = file_response(b"refreshed")
        refreshed = cache.fetch(("user", "revision-one", "manifest"), load)
        self.assertEqual(b"".join(refreshed[0]), b"refreshed")
        self.assertEqual(load.call_count, 3)

    def test_lru_and_byte_limits_bound_memory(self):
        cache = BoundedFileCache(max_bytes=8, max_file_bytes=4, max_entries=2)
        for name in ("a", "b"):
            cache.fetch(name, lambda: file_response())
        cache.fetch("a", Mock(side_effect=AssertionError("cache miss")))
        cache.fetch("c", lambda: file_response())
        self.assertEqual(list(cache._entries), ["a", "c"])
        self.assertEqual(cache._bytes, 8)
        cache.fetch("b", lambda: file_response(b"x"))
        self.assertEqual(cache._bytes, 5)
        self.assertEqual(len(cache._entries), 2)

    def test_large_files_keep_streaming_without_entering_cache(self):
        cache = BoundedFileCache(max_file_bytes=3)
        consumed = Mock()
        def stream():
            consumed()
            yield b"large"
        result = (stream(), "application/octet-stream", 5, Mock())
        self.assertIs(cache.fetch("large", lambda: result), result)
        consumed.assert_not_called()
        self.assertFalse(cache._entries)
        self.assertEqual(b"".join(result[0]), b"large")

    def test_failed_or_incomplete_downloads_are_not_cached(self):
        cache = BoundedFileCache()
        close = Mock()
        for loader in (Mock(side_effect=FileNotFoundError()),
                       lambda: (iter((b"short",)), "application/octet-stream", 10, close)):
            with self.assertRaises((FileNotFoundError, IOError)):
                cache.fetch("file", loader)
            self.assertFalse(cache._entries)
            self.assertFalse(cache._loading)
        close.assert_called_once()
        good = cache.fetch("file", lambda: file_response())
        self.assertEqual(b"".join(good[0]), b"data")


class SSHPerformanceTests(unittest.TestCase):
    def connection(self):
        connection = Mock()
        connection.get_transport.return_value.is_active.return_value = True
        connection.get_transport.return_value.is_authenticated.return_value = True
        connection.exec_command.return_value = (Mock(), Mock(), Mock())
        return connection

    def test_key_load_is_shared_and_refreshes_after_expiry_or_configuration_change(self):
        stamp = [0]
        cache = ExpiringKey(ttl=5, clock=lambda: stamp[0])
        loader = Mock(side_effect=["old", "rotated", "other-source"])
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertEqual(list(executor.map(lambda _: cache.get("source", loader), range(4))), ["old"] * 4)
        stamp[0] = 6
        self.assertEqual(cache.get("source", loader), "rotated")
        self.assertEqual(cache.get("new-source", loader), "other-source")
        self.assertEqual(loader.call_count, 3)

    def test_authentication_failure_refreshes_cached_key_once(self):
        cache = ExpiringKey()
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                patch.object(service.performance, "ssh_key", cache), \
                patch.object(service, "_load_ssh_key", side_effect=["old", "new"]) as load, \
                patch.object(service, "_connect_with_key", side_effect=[paramiko.AuthenticationException(), "connection"]) as connect:
            self.assertEqual(service._connect_remote(), "connection")
        self.assertEqual(load.call_count, 2)
        self.assertEqual([call.args[0] for call in connect.call_args_list], ["old", "new"])

    def test_completed_reads_reuse_connection_and_close_only_command_channel(self):
        pool = SSHReadPool(limit=1)
        connection = self.connection()
        connect = Mock(return_value=connection)
        lease = pool.acquire("vm", connect)
        lease.exec_command("read")
        lease.mark_complete()
        lease.close()
        lease.close()
        connection.exec_command.return_value[1].channel.close.assert_called_once()
        connection.close.assert_not_called()
        reused = pool.acquire("vm", connect)
        connect.assert_called_once()
        reused.mark_complete()
        reused.close()
        pool.close()
        connection.close.assert_called_once()

    def test_early_exit_discards_connection_and_pool_is_bounded(self):
        pool = SSHReadPool(limit=1)
        first, second = self.connection(), self.connection()
        connect = Mock(side_effect=[first, second])
        lease = pool.acquire("vm", connect)
        with self.assertRaises(TimeoutError):
            pool.acquire("vm", connect, timeout=0.01)
        lease.close()
        first.close.assert_called_once()
        replacement = pool.acquire("vm", connect)
        replacement.mark_complete()
        replacement.close()
        self.assertEqual(connect.call_count, 2)
        pool.close()

    def test_idle_expiry_endpoint_change_and_dead_transport_discard_sessions(self):
        stamp = [0]
        pool = SSHReadPool(limit=1, idle_seconds=5, clock=lambda: stamp[0])
        connections = [self.connection() for _ in range(4)]
        connect = Mock(side_effect=connections)
        for identity, stamp_value in (("vm", 0), ("vm", 6), ("another-vm", 6), ("another-vm", 6)):
            stamp[0] = stamp_value
            lease = pool.acquire(identity, connect)
            lease.mark_complete()
            lease.close()
            if connect.call_count == 3:
                connections[2].get_transport.return_value.is_active.return_value = False
        self.assertEqual(connect.call_count, 4)
        for connection in connections[:3]:
            connection.close.assert_called_once()
        pool.close()

    def test_source_and_data_jobs_use_dedicated_connections(self):
        for action in ("sources", "data"):
            connection = self.connection()
            connection.exec_command.return_value = (Mock(), Mock(), Mock())
            with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                    patch.object(service, "_connect_remote", return_value=connection), \
                    patch.object(service.performance.ssh_reads, "acquire") as acquire:
                result = service._open_remote({"action": action, "source_user": "wilson_sgroi", "timeout": 5})
            acquire.assert_not_called()
            self.assertIs(result[0], connection)

    def test_stale_connection_is_replaced_before_retrying_read_only_command(self):
        pool = SSHReadPool(limit=1)
        stale, working = self.connection(), self.connection()
        stale.exec_command.side_effect = EOFError()
        working.exec_command.return_value = (Mock(), Mock(), Mock())
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                patch.object(service.performance, "ssh_reads", pool), \
                patch.object(service, "_connect_remote", side_effect=[stale, working]) as connect:
            lease, _, _ = service._open_remote({"action": "read", "source_user": "wilson_sgroi", "timeout": 5})
        self.assertEqual(connect.call_count, 2)
        stale.close.assert_called_once()
        lease.close()
        pool.close()

    def test_missing_optional_table_does_not_discard_healthy_connection(self):
        pool = SSHReadPool(limit=1)
        connection = self.connection()
        output = io.BytesIO(b'{"error": "File non disponibile"}\n')
        output.channel = Mock()
        output.channel.recv_exit_status.return_value = 1
        connection.exec_command.return_value = (Mock(), output, io.BytesIO())
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                patch.object(service.performance, "ssh_reads", pool), \
                patch.object(service, "_connect_remote", return_value=connection) as connect:
            with self.assertRaises(FileNotFoundError):
                service._remote_file({"action": "read", "source_user": "wilson_sgroi", "timeout": 5},
                                     service.PurePosixPath("gold_monitoring_dashboard/data/optional.parquet"))
            lease = pool.acquire(service._remote_identity(), service._connect_remote)
        connect.assert_called_once()
        connection.close.assert_not_called()
        lease.close()
        pool.close()

    def test_disable_switch_uses_direct_read_connection(self):
        connection = self.connection()
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "false"}), \
                patch.object(service, "_connect_remote", return_value=connection), \
                patch.object(service.performance.ssh_reads, "acquire") as acquire:
            result = service._open_remote({"action": "read", "source_user": "wilson_sgroi", "timeout": 5})
        acquire.assert_not_called()
        self.assertIs(result[0], connection)


class FastTrackOptimizedIntegrationTests(unittest.TestCase):
    complete = baseline.FastTrackTests.complete

    def setUp(self):
        baseline.FastTrackTests.setUp(self)
        self.cache = BoundedFileCache()
        self.cache_patch = patch.object(service.performance, "files", self.cache)
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        baseline.FastTrackTests.tearDown(self)

    def publish(self, revision, user="wilson_sgroi"):
        self.complete("data", {"publication:" + revision: {"revision": revision, "source_user": user}})

    def test_cache_hits_still_require_authentication_and_reject_forbidden_paths(self):
        revision = "b" * 32
        self.publish(revision)
        path = f"/api/fast-track/content/{revision}/gold_monitoring_dashboard/data/clients.json"
        output = io.BytesIO(b'{"size": 4}\ndata')
        output.channel = Mock()
        output.channel.recv_exit_status.return_value = 0
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                patch.object(service, "_open_remote", return_value=(Mock(), output, io.BytesIO())) as remote:
            for _ in range(2):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"data")
                self.assertIn("private", response.headers["cache-control"])
            self.assertEqual(remote.call_count, 1)
            with self.assertRaises(FileNotFoundError):
                service.publication_file("e" * 32, "gold_monitoring_dashboard/data/clients.json")
            self.client.app.dependency_overrides.clear()
            with patch.dict(os.environ, {"WEBSITE_SITE_NAME": "cloud", "FAST_TRACK_AUTH_MODE": "linked", "WEBSITE_AUTH_ENABLED": "true"}):
                self.assertEqual(self.client.get(path).status_code, 401)
            for name in ("gold_monitoring_dashboard/data/model.rds", "gold_monitoring_dashboard/data/../secret.json"):
                with self.assertRaises(FileNotFoundError):
                    service.publication_file(revision, name)
            self.assertEqual(remote.call_count, 1)

    def test_new_publication_and_source_user_cannot_reuse_old_bytes(self):
        revisions = ("b" * 32, "c" * 32, "d" * 32)
        for revision, user in zip(revisions, ("wilson_sgroi", "wilson_sgroi", "lorenzo_rosso")):
            self.publish(revision, user)
        loader = Mock(side_effect=[file_response(b"old"), file_response(b"new"), file_response(b"lorenzo")])
        with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}), \
                patch.object(service, "_remote_file", loader):
            contents = [b"".join(service.publication_file(revision, "gold_monitoring_dashboard/data/clients.json")[0])
                        for revision in revisions]
        self.assertEqual(contents, [b"old", b"new", b"lorenzo"])
        self.assertEqual(loader.call_count, 3)

    def test_disable_switch_bypasses_cached_data(self):
        revision = "b" * 32
        self.publish(revision)
        name = "gold_monitoring_dashboard/data/clients.json"
        loader = Mock(side_effect=[file_response(b"cached"), file_response(b"direct")])
        with patch.object(service, "_remote_file", loader):
            with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "true"}):
                self.assertEqual(b"".join(service.publication_file(revision, name)[0]), b"cached")
            with patch.dict(os.environ, {"FAST_TRACK_OPTIMIZATIONS_ENABLED": "false"}):
                self.assertEqual(b"".join(service.publication_file(revision, name)[0]), b"direct")


if __name__ == "__main__":
    unittest.main()
