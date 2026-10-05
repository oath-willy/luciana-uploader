import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from services.mc_code_local_store import runtime_path


class PdbRuntimePathTests(unittest.TestCase):
    def test_new_items_runtime_has_a_predictable_name_and_migrates_legacy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "runtime.sqlite3"
            with closing(sqlite3.connect(legacy)) as connection:
                connection.execute("CREATE TABLE migration_fixture (value TEXT)")
                connection.execute("INSERT INTO migration_fixture VALUES ('preserved')")
                connection.commit()

            with patch.dict(os.environ, {
                "MC_CODE_LOCAL_DATA_DIR": str(root),
                "MC_CODE_RUNTIME_DB": str(legacy),
                "PDB_NEW_ITEMS_RUNTIME_DB": "",
            }):
                migrated = runtime_path()

            self.assertEqual(migrated.name, "runtime_pdb_new_items.sqlite3")
            self.assertTrue(legacy.is_file())
            with closing(sqlite3.connect(migrated)) as connection:
                value = connection.execute(
                    "SELECT value FROM migration_fixture"
                ).fetchone()[0]
            self.assertEqual(value, "preserved")


if __name__ == "__main__":
    unittest.main()
