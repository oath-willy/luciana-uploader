"""Read-only benchmark against the local Reference PDB; no SQL or worker calls."""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.items_code import _columns, _company_expression, _schema, _stamp, dataset_path, search_dataset
from services.items_code_browse_cache import matches, prepare_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", help="Override ref_pdb_dump.parquet location")
    parser.add_argument("--search", default="ketac")
    parser.add_argument("--company", default="IVOCLAR")
    args = parser.parse_args()
    if args.path:
        os.environ["ITEMS_CODE_PDB_LOCAL_PATH"] = args.path
    os.environ["ITEMS_CODE_BROWSE_CACHE_ENABLED"] = "true"
    path = dataset_path("pdb")
    stamp = _stamp(path)
    _, expressions = _columns(stamp, "pdb", "")
    started = time.perf_counter()
    prepared = prepare_snapshot(path, expressions, _company_expression(_schema(stamp)))
    print(json.dumps({"preparation_seconds": round(time.perf_counter() - started, 3),
                      "cache_file_mb": round(prepared.stat().st_size / 1024 / 1024, 1)}), flush=True)

    def query(label, options, barrier=None):
        params = dict(company="", page=0, page_size=100, search="", filters={})
        params.update(options)
        if barrier:
            barrier.wait(timeout=30)
        started = time.perf_counter()
        result = search_dataset("pdb", **params)
        return {"query": label, "seconds": round(time.perf_counter() - started, 3),
                "total": result["total"], "page_rows": len(result["rows"])}

    print(json.dumps(query("initial-all-companies", {})), flush=True)
    print(json.dumps(query("deep-page", {"page": 10000})), flush=True)
    cases = [("generic", {"search": args.search}), ("description", {"filters": {"description": args.search}}),
             ("company", {"company": args.company}), ("master", {"filters": {"master_code": "02_03_01"}})]
    barrier = threading.Barrier(4)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda case: query(*case, barrier), cases))
    print(json.dumps({"four_concurrent_seconds": round(time.perf_counter() - started, 3), "results": results}), flush=True)
    print(json.dumps(query("cached-generic-next-page", {"search": args.search, "page": 1})), flush=True)
    print(json.dumps({"match_cache_bytes": matches._bytes, "match_cache_entries": len(matches._entries)}), flush=True)


if __name__ == "__main__":
    main()
