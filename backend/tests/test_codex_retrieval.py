import unittest

from services.codex_retrieval import (
    MAX_LOOKUP_BATCH_SIZE,
    PdbBm25Retriever,
    RetrievalItem,
    normalize_retrieval_description,
)


class _FakeDatabricksClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, parameters=None, timeout_seconds=None):
        self.calls.append((sql, parameters, timeout_seconds))
        return [dict(row) for row in self.rows]


class CodexRetrievalTests(unittest.TestCase):
    def test_normalization_removes_control_master_code(self):
        self.assertEqual(
            normalize_retrieval_description(
                "DENTAL estimated category | 20_02_01 VIBRACAP 400-M"
            ),
            "vibracap 400 m",
        )

    def test_retrieve_requires_exactly_three_results_per_item(self):
        client = _FakeDatabricksClient(
            [
                {
                    "query_item_code": "A1",
                    "identity_rank": rank,
                    "identity_score": 1 / rank,
                    "exact_match": rank == 1,
                    "pdb_ref": f"PDB-{rank}",
                }
                for rank in range(1, 4)
            ]
        )
        retriever = PdbBm25Retriever(client, "catalog.schema.pdb")

        result = retriever.retrieve([RetrievalItem("A1", "test product")], 12)

        self.assertEqual([row["identity_rank"] for row in result["A1"]], [1, 2, 3])
        self.assertIn("VERSION AS OF 12", client.calls[0][0])

    def test_retrieve_rejects_batches_above_limit(self):
        retriever = PdbBm25Retriever(_FakeDatabricksClient([]), "pdb")
        items = [
            RetrievalItem(str(index), f"description {index}")
            for index in range(MAX_LOOKUP_BATCH_SIZE + 1)
        ]

        with self.assertRaisesRegex(ValueError, "al massimo"):
            retriever.retrieve(items, 1)


if __name__ == "__main__":
    unittest.main()
