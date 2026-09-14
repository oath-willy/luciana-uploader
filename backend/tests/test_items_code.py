import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.items_code import router


class ItemsCodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "MC_CODE_LOCAL_DATA_DIR": str(self.root),
            "PDB_REF_LOCAL_PATH": str(self.root / "ref_pdb_dump.parquet"),
            "ITEMS_CODE_PDB_LOCAL_PATH": "",
            "ITEMS_CODE_BROWSE_CACHE_ENABLED": "false",
        })
        self.environment.start()
        extras = {f"field_{index}": [f"value{index}"] for index in range(15)}
        extras["odd.'key"] = ["100%_literal"]
        pq.write_table(pa.Table.from_pylist([
            {"company": "ACME", "item_code": f"{index:04}", "description": "fixture",
             "item_extra_descriptions": json.dumps(extras)} for index in range(1100)
        ] + [{"company": "OTHER", "item_code": "1", "description": "outside", "item_extra_descriptions": '{"other_field":"other"}'}]), self.root / "pdb_new_items.parquet")
        pq.write_table(pa.Table.from_pylist([
            {"company_item_code": "ACME|1", "dealer_company_name": "ACME", "description": "alpha", "extra": "100%_literal",
             "mc_lvl1_code": "2", "mc_lvl2_code": "03", "mc_lvl3_code": "0", "pack": "Box", "brand_name": "brand", "last_update": "2026-01-01"},
            {"company_item_code": "OTHER|2", "dealer_company_name": "OTHER", "description": "beta", "extra": "100xxliteral",
             "mc_lvl1_code": None, "mc_lvl2_code": "3", "mc_lvl3_code": "1", "pack": "Bag", "brand_name": "brand", "last_update": "2026-01-01"},
        ]), self.root / "ref_pdb_dump.parquet")
        app = FastAPI()
        app.include_router(router, prefix="/api")
        self.client = TestClient(app)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def search(self, dataset, **kwargs):
        return self.client.post(f"/api/items-code/{dataset}/search", json=kwargs)

    def test_company_required_and_json_schema_has_no_twelve_column_cap(self):
        self.assertEqual(self.search("new-items").status_code, 400)
        meta = self.client.get("/api/items-code/new-items/metadata?company=ACME").json()
        self.assertEqual(meta["companies"], ["ACME", "OTHER"])
        self.assertIn("item_extra_descriptions.field_14", [column["field"] for column in meta["columns"]])
        other = self.client.get("/api/items-code/new-items/metadata?company=OTHER").json()
        self.assertNotIn("item_extra_descriptions.field_14", [column["field"] for column in other["columns"]])

    def test_server_pagination_and_json_filters_cover_all_matching_rows(self):
        first = self.search("new-items", company="ACME", page_size=1000,
                            filters={"item_extra_descriptions.odd.'key": "100%_literal"}).json()
        second = self.search("new-items", company="ACME", page_size=1000, page=1).json()
        self.assertEqual(first["total"], 1100)
        self.assertEqual(len(first["rows"]), 1000)
        self.assertEqual(len(second["rows"]), 100)
        self.assertNotEqual(first["rows"][0]["__items_code_row_id"], second["rows"][0]["__items_code_row_id"])
        self.assertEqual(first["rows"][0]["item_extra_descriptions.field_14"], ["value14"])

    def test_pdb_company_and_general_and_column_filters(self):
        all_rows = self.search("pdb").json()
        self.assertEqual(all_rows["total"], 2)
        self.assertEqual(self.search("pdb", company="OTHER").json()["total"], 1)
        self.assertEqual(self.search("pdb", search="beta").json()["rows"][0]["dealer_company_name"], "OTHER")
        self.assertEqual(self.search("pdb", filters={"extra": "%_"}).json()["total"], 1)
        self.assertEqual(self.search("pdb", filters={"description": "no-match"}).json()["total"], 0)

    def test_invalid_filters_and_pagination_and_missing_file(self):
        for payload in ({"filters": {"description);drop table source;--": "x"}}, {"page": -1}, {"page_size": 99999}):
            self.assertIn(self.search("pdb", **payload).status_code, (400, 422))
        (self.root / "ref_pdb_dump.parquet").unlink()
        self.assertFalse(self.client.get("/api/items-code/pdb/metadata").json()["available"])
        self.assertEqual(self.search("pdb").status_code, 503)

    def test_new_parquet_replacement_invalidates_metadata_cache(self):
        before = self.client.get("/api/items-code/pdb/metadata").json()
        self.assertEqual(before["companies"], ["ACME", "OTHER"])
        pq.write_table(pa.Table.from_pylist([{"company": "NEW", "description": "new"}]), self.root / "ref_pdb_dump.parquet")
        after = self.client.get("/api/items-code/pdb/metadata").json()
        self.assertEqual(after["companies"], ["NEW"])

    def test_master_code_and_support_columns_are_not_copied_from_reference(self):
        reference = self.search("pdb", filters={"master_code": "02_03_00"}).json()
        self.assertEqual(reference["total"], 1)
        self.assertEqual(reference["rows"][0]["master_code"], "02_03_00")
        fields = [column["field"] for column in reference["columns"]]
        self.assertNotIn("mc_lvl1_code", fields)
        self.assertEqual(fields.count("master_code"), 1)
        self.assertIsNone(self.search("pdb", company="OTHER").json()["rows"][0]["master_code"])
        upper = self.search("new-items", company="ACME").json()
        fields = [column["field"] for column in upper["columns"]]
        self.assertLess(fields.index("item_extra_descriptions.field_14"), fields.index("master_code"))
        self.assertNotIn("brand_name", fields)
        self.assertNotIn("last_update", fields)
        self.assertIsNone(upper["rows"][0]["master_code"])
        self.assertIsNone(upper["rows"][0]["pack"])
        self.assertEqual(self.search("new-items", company="ACME", filters={"pack": "Box"}).json()["total"], 0)

    def test_support_schema_available_when_reference_is_missing(self):
        (self.root / "ref_pdb_dump.parquet").unlink()
        upper = self.search("new-items", company="ACME").json()
        self.assertEqual(upper["total"], 1100)
        self.assertIsNone(upper["rows"][0]["master_code"])
        self.assertIn("inner_qty", upper["rows"][0])


if __name__ == "__main__":
    unittest.main()
