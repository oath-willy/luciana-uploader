from collections import OrderedDict
from concurrent.futures import Future
from threading import Lock


class CompanyCache:
    """Bounded immutable Arrow tables; edits are deliberately never cached."""

    def __init__(self, max_bytes=64 * 1024 * 1024, max_entries=8):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.entries = OrderedDict()
        self.pending = {}
        self.bytes = 0
        self.lock = Lock()

    def get(self, key, loader):
        with self.lock:
            if key in self.entries:
                self.entries.move_to_end(key)
                return self.entries[key]
            future = self.pending.get(key)
            owner = future is None
            if owner:
                future = Future()
                self.pending[key] = future
        if not owner:
            return future.result()
        try:
            table = loader()
            with self.lock:
                if table.nbytes <= self.max_bytes:
                    while self.entries and (self.bytes + table.nbytes > self.max_bytes or len(self.entries) >= self.max_entries):
                        _, evicted = self.entries.popitem(last=False)
                        self.bytes -= evicted.nbytes
                    self.entries[key] = table
                    self.bytes += table.nbytes
            future.set_result(table)
            return table
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)


companies = CompanyCache()
