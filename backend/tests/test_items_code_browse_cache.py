import os
import tempfile
import threading
import time
import unittest
from array import array
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from services.items_code import _columns, _company_expression, _matching_ids, _schema, _stamp, search_dataset
from services.items_code_browse_cache import MatchCache, prepare_snapshot


class MatchCacheTests(unittest.TestCase):
    def test_reuse_and_bounded_eviction(self):
        cache = MatchCache(max_bytes=24, max_entries=2)
        calls = []

        def load():
            calls.append(True)
            return 2, array("Q", [1, 2])

        cache.get((1,), load)
        cache.get((1,), load)
        self.assertEqual(len(calls), 1)
        cache.get((2,), load)
        self.assertLessEqual(cache._bytes, 24)
        self.assertNotIn((1,), cache._entries)
        for key in range(3, 10):
            cache.get((key,), lambda: (0, array("Q")))
        self.assertEqual(len(cache._entries), 2)

    def test_four_identical_concurrent_requests_share_one_scan(self):
        cache = MatchCache()
        start = threading.Barrier(4)
        calls = []

        def request():
            start.wait(timeout=5)
            return cache.get(("same-filter",), load)

        def load():
            calls.append(True)
            time.sleep(0.05)
            return 3, array("Q", [1, 2, 3])

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: request(), range(4)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(result == results[0] for result in results))

    def test_failed_scan_can_be_retried(self):
        cache = MatchCache()
        with self.assertRaises(ValueError):
            cache.get((1,), lambda: (_ for _ in ()).throw(ValueError("failed")))
        self.assertEqual(cache.get((1,), lambda: (0, array("Q")))[0], 0)


class PreparedReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ref_pdb_dump.parquet"
        self.environment = patch.dict(os.environ, {
            "ITEMS_CODE_PDB_LOCAL_PATH": str(self.path),
            "ITEMS_CODE_BROWSE_CACHE_DIR": str(Path(self.temp.name) / "cache"),
            "ITEMS_CODE_BROWSE_CACHE_ENABLED": "false",
        })
        self.environment.start()
        descriptions = ["alpha", "Straße école", "100%_literal", "slash\\text", "alpha\x00omega"]
        pq.write_table(pa.Table.from_pylist([
            {"company_item_code": f"COMPANY{index % 3}|{index}", "dealer_company_name": f"Company{index % 3}",
             "description": descriptions[index % len(descriptions)], "brand_name": "omega",
             "mc_lvl1_code": "2", "mc_lvl2_code": "03", "mc_lvl3_code": "0",
             "inner_count": Decimal("2.000000"), "last_update": datetime(2026, 1, 1)}
            for index in range(350)
        ]), self.path)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def prepare(self):
        stamp = _stamp(self.path)
        _, expressions = _columns(stamp, "pdb", "")
        return prepare_snapshot(self.path, expressions, _company_expression(_schema(stamp)))

    def search(self, **kwargs):
        params = dict(company="", page=0, page_size=25, search="", filters={})
        params.update(kwargs)
        return search_dataset("pdb", **params)

    def test_prepared_results_preserve_all_filters_types_order_and_ids(self):
        cases = [
            {}, {"company": "company1"}, {"page": 13}, {"page": 99},
            {"search": "alpha"}, {"search": "ÉCOLE"}, {"search": "Straße"},
            {"search": "%_"}, {"search": "slash\\text"}, {"search": "alpha\x00omega"},
            {"search": "alphaomega"}, {"search": "2.000000"}, {"search": "2026-01-01"},
            {"filters": {"master_code": "02_03_00"}},
            {"company": "company2", "search": "omega", "filters": {"description": "alpha", "inner_count": "2.0"}},
            {"filters": {"description": "no match"}}, {"search": "alpha", "page": 4},
        ]
        before = [self.search(**case) for case in cases]
        prepared = self.prepare()
        self.assertTrue(prepared.is_file())
        with patch.dict(os.environ, {"ITEMS_CODE_BROWSE_CACHE_ENABLED": "true"}):
            after = [self.search(**case) for case in cases]
        self.assertEqual(before, after)
        self.assertEqual(after[0]["total"], 350)
        self.assertEqual(len(after[0]["rows"]), 25)
        self.assertEqual(after[2]["rows"][0]["__items_code_row_id"], 325)

    def test_replacement_has_a_new_snapshot_and_new_filter_cache(self):
        first = self.prepare()
        with patch.dict(os.environ, {"ITEMS_CODE_BROWSE_CACHE_ENABLED": "true"}):
            self.assertEqual(self.search(search="alpha")["total"], 140)
        pq.write_table(pa.Table.from_pylist([{"company": "NEW", "description": "alpha"}]), self.path)
        second = self.prepare()
        self.assertNotEqual(first, second)
        with patch.dict(os.environ, {"ITEMS_CODE_BROWSE_CACHE_ENABLED": "true"}):
            result = self.search(search="alpha")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["company"], "NEW")

    def test_concurrent_preparation_publishes_only_one_complete_file(self):
        with patch("services.items_code_browse_cache.duckdb.connect", wraps=duckdb.connect) as connect:
            # Resolve schema before counting only the expensive COPY connections.
            _columns(_stamp(self.path), "pdb", "")
            connect.reset_mock()
            with ThreadPoolExecutor(max_workers=2) as pool:
                files = list(pool.map(lambda _: self.prepare(), range(2)))
            self.assertEqual(files[0], files[1])
            self.assertEqual(connect.call_count, 1)
        with duckdb.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM read_parquet(?)", [str(files[0])]).fetchone()[0], 350)

    def test_large_match_set_uses_bounded_count_only_fallback(self):
        with patch("services.items_code.MATCH_CACHE_BYTES", 16):
            self.assertEqual(self.search(filters={"master_code": "02_03_00"}, page=2)["rows"][0]["__items_code_row_id"], 50)

    def test_identifiers_are_compact_without_overflow_for_large_files(self):
        total, ids = _matching_ids(self.path, "file_row_number", "", [])
        self.assertEqual((total, ids.typecode), (350, "I"))
        large = self.path.parent / "large-identifiers.parquet"
        pq.write_table(pa.Table.from_pylist([{"row_id": value} for value in (0, 2**32, 2**32 + 1)]), large)
        total, ids = _matching_ids(large, '"row_id"', "", [])
        self.assertEqual((total, ids.typecode), (3, "Q"))
        self.assertEqual(list(ids), [0, 2**32, 2**32 + 1])


if __name__ == "__main__":
    unittest.main()
