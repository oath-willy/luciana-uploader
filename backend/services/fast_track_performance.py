"""Bounded, process-local Fast Track optimizations, independent of dashboard sources."""
from __future__ import annotations

import atexit
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable


def optimizations_enabled() -> bool:
    return os.getenv("FAST_TRACK_OPTIMIZATIONS_ENABLED", "true").lower() == "true"


class ExpiringKey:
    """Load credentials once per interval; concurrent callers share the same load."""

    def __init__(self, ttl: float = 300, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock = ttl, clock
        self._lock = threading.Lock()
        self._identity = None
        self._value = None
        self._expires = 0.0

    def get(self, identity: Any, load: Callable[[], Any]):
        with self._lock:
            if self._identity != identity or self._value is None or self.clock() >= self._expires:
                # Failed loads are never cached, including after a configuration change.
                self._identity, self._value, self._expires = None, None, 0.0
                value = load()
                self._identity, self._value, self._expires = identity, value, self.clock() + self.ttl
            return self._value

    def clear(self):
        with self._lock:
            self._identity, self._value, self._expires = None, None, 0.0


@dataclass
class _Connection:
    client: Any
    created_at: float
    idle_at: float


class SSHLease:
    """Exclusive connection use; only fully consumed commands may return to the pool."""

    def __init__(self, pool: "SSHReadPool", connection: _Connection, identity: Any):
        self._pool, self._connection, self._identity = pool, connection, identity
        self._channel = None
        self._complete = False
        self._closed = False
        self._lock = threading.Lock()

    def exec_command(self, *args, **kwargs):
        streams = self._connection.client.exec_command(*args, **kwargs)
        self._channel = streams[1].channel
        return streams

    def mark_complete(self):
        self._complete = True

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            complete = self._complete
            if self._channel is not None:
                try:
                    self._channel.close()
                except Exception:
                    complete = False
            self._pool.release(self._connection, self._identity, complete)


class SSHReadPool:
    """At most four exclusive SSH sessions, with bounded idle time and credential age."""

    def __init__(self, limit: int = 4, idle_seconds: float = 60, lifetime_seconds: float = 300,
                 clock: Callable[[], float] = time.monotonic):
        self.limit, self.idle_seconds, self.lifetime_seconds = limit, idle_seconds, lifetime_seconds
        self.clock = clock
        self._condition = threading.Condition()
        self._identity = None
        self._idle: list[_Connection] = []
        self._connections: dict[int, _Connection] = {}
        self._count = 0
        self._closed = False

    def _healthy(self, connection: _Connection) -> bool:
        transport = connection.client.get_transport()
        return bool(transport and transport.is_active() and transport.is_authenticated())

    def _discard(self, connection: _Connection):
        self._connections.pop(id(connection), None)
        self._count -= 1
        connection.client.close()

    def acquire(self, identity: Any, connect: Callable[[], Any], timeout: float = 20) -> SSHLease:
        deadline = self.clock() + timeout
        with self._condition:
            while True:
                if self._closed:
                    raise RuntimeError("Pool Fast Track chiuso")
                if identity != self._identity:
                    for connection in self._idle:
                        self._discard(connection)
                    self._idle.clear()
                    self._identity = identity
                stamp = self.clock()
                # Expire every idle session, including ones below the most recently used one.
                for connection in list(self._idle):
                    if (stamp - connection.idle_at >= self.idle_seconds
                            or stamp - connection.created_at >= self.lifetime_seconds
                            or not self._healthy(connection)):
                        self._idle.remove(connection)
                        self._discard(connection)
                if self._idle:
                    return SSHLease(self, self._idle.pop(), identity)
                if self._count < self.limit:
                    self._count += 1
                    break
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError("Connessioni Fast Track occupate")
                self._condition.wait(remaining)
        try:
            client = connect()
            connection = _Connection(client, self.clock(), self.clock())
        except BaseException:
            with self._condition:
                self._count -= 1
                self._condition.notify_all()
            raise
        with self._condition:
            if self._closed:
                self._count -= 1
                client.close()
                raise RuntimeError("Pool Fast Track chiuso")
            self._connections[id(connection)] = connection
        return SSHLease(self, connection, identity)

    def release(self, connection: _Connection, identity: Any, complete: bool):
        with self._condition:
            if id(connection) not in self._connections:
                return
            if (self._closed or not complete or identity != self._identity
                    or self.clock() - connection.created_at >= self.lifetime_seconds
                    or not self._healthy(connection)):
                self._discard(connection)
            else:
                connection.idle_at = self.clock()
                self._idle.append(connection)
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self._closed = True
            for connection in list(self._connections.values()):
                self._discard(connection)
            self._idle.clear()
            self._condition.notify_all()


class BoundedFileCache:
    """Private bytes cache, with LRU/TTL limits and a single loader for each file."""

    def __init__(self, max_bytes: int = 32 * 1024 * 1024, max_file_bytes: int = 8 * 1024 * 1024,
                 max_entries: int = 512, ttl: float = 300, clock: Callable[[], float] = time.monotonic):
        self.max_bytes, self.max_file_bytes, self.max_entries, self.ttl = max_bytes, max_file_bytes, max_entries, ttl
        self.clock = clock
        self._condition = threading.Condition()
        self._entries: OrderedDict[Any, tuple[float, bytes, str]] = OrderedDict()
        self._loading: set[Any] = set()
        self._bytes = 0

    def _prune(self):
        for key, (expires, payload, _) in list(self._entries.items()):
            if self.clock() >= expires:
                self._bytes -= len(payload)
                del self._entries[key]

    @staticmethod
    def _response(payload: bytes, mime: str):
        return iter((payload,)), mime, len(payload), lambda: None

    def fetch(self, key: Any, load: Callable[[], tuple], timeout: float = 30):
        deadline = self.clock() + timeout
        with self._condition:
            while True:
                self._prune()
                entry = self._entries.get(key)
                if entry is not None:
                    self._entries.move_to_end(key)
                    return self._response(entry[1], entry[2])
                if key not in self._loading:
                    self._loading.add(key)
                    break
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError("Lettura Fast Track gia in corso")
                self._condition.wait(remaining)
        try:
            result = load()
            iterator, mime, size, close = result
            if size > min(self.max_file_bytes, self.max_bytes):
                return result
            try:
                payload = b"".join(iterator)
                if len(payload) != size:
                    raise IOError("Trasferimento dati incompleto")
            finally:
                close()
            with self._condition:
                self._prune()
                while self._entries and (self._bytes + size > self.max_bytes or len(self._entries) >= self.max_entries):
                    _, entry = self._entries.popitem(last=False)
                    self._bytes -= len(entry[1])
                self._entries[key] = self.clock() + self.ttl, payload, mime
                self._bytes += size
            return self._response(payload, mime)
        finally:
            with self._condition:
                self._loading.remove(key)
                self._condition.notify_all()

    def clear(self):
        with self._condition:
            self._entries.clear()
            self._bytes = 0


ssh_key = ExpiringKey()
ssh_reads = SSHReadPool()
files = BoundedFileCache()
atexit.register(ssh_reads.close)
