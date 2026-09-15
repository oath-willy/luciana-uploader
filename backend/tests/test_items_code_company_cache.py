import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pyarrow as pa
from services.items_code_company_cache import CompanyCache


class CompanyCacheTests(unittest.TestCase):
    def test_bounded_lru_and_source_stamp(self):
        table = pa.table({"value": ["example"]})
        cache = CompanyCache(max_bytes=table.nbytes * 2, max_entries=2)
        calls = []
        def load():
            calls.append(1)
            return table
        cache.get((1, "A"), load)
        cache.get((1, "B"), load)
        cache.get((1, "A"), load)
        cache.get((2, "A"), load)
        self.assertNotIn((1, "B"), cache.entries)
        self.assertEqual(len(calls), 3)
        self.assertLessEqual(cache.bytes, cache.max_bytes)

    def test_oversized_table_and_failure_are_not_retained(self):
        cache = CompanyCache(max_bytes=1)
        table = pa.table({"value": ["example"]})
        cache.get("large", lambda: table)
        self.assertFalse(cache.entries)
        def fail():
            raise ValueError("fixture")
        with self.assertRaises(ValueError):
            cache.get("failed", fail)
        self.assertIs(cache.get("failed", lambda: table), table)

    def test_concurrent_load_is_coalesced(self):
        cache = CompanyCache()
        started, release = Event(), Event()
        calls = []
        table = pa.table({"value": ["example"]})
        def load():
            calls.append(1)
            started.set()
            release.wait(5)
            return table
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(cache.get, "A", load)
            self.assertTrue(started.wait(5))
            others = [pool.submit(cache.get, "A", load) for _ in range(3)]
            release.set()
            self.assertIs(first.result(), table)
            self.assertTrue(all(f.result() is table for f in others))
        self.assertEqual(len(calls), 1)
