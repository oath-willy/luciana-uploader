import unittest

from services.codex_coherence import assess_candidate_taxonomy, decide_bs25ai_route
from services.codex_retrieval import (
    MAX_LOOKUP_BATCH_SIZE,
    PdbBm25Retriever,
    RetrievalItem,
    normalize_retrieval_description,
)
from services.codex_selection import resolve_codex_selection


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


class CodexCoherenceTests(unittest.TestCase):
    def test_heraceram_cre_active_is_coherent_but_fuzzy_routes_to_sol_low(self):
        proposals = [
            {
                "identity_rank": rank,
                "pdb_description": "HeraCeram cre-active color indication",
                "manufacturer": "KULZER",
                "master_code": "38_02_02",
                "exact_match": False,
            }
            for rank in range(1, 4)
        ]

        assessment = assess_candidate_taxonomy(proposals)
        decision = decide_bs25ai_route(proposals)

        self.assertTrue(assessment.is_coherent)
        self.assertEqual(assessment.reason, "coherent_taxonomy")
        self.assertEqual(decision.route, "sol_low")
        self.assertIn("tassonomicamente coerenti", decision.flag)

    def test_heraceram_towel_candidates_require_escalation(self):
        proposals = [
            {
                "identity_rank": 1,
                "pdb_description": "TOWEL",
                "manufacturer": "BK MEDENT",
                "master_code": "09_05_03",
            },
            {
                "identity_rank": 2,
                "pdb_description": "Creation Handtücher / Towel",
                "manufacturer": "CREATION-WILLIGELLER",
                "master_code": "91_03_00",
            },
            {
                "identity_rank": 3,
                "pdb_description": "GC Initial Towel",
                "manufacturer": "GC",
                "master_code": "38_09_99",
            },
        ]

        assessment = assess_candidate_taxonomy(proposals)
        decision = decide_bs25ai_route(proposals)

        self.assertFalse(assessment.is_coherent)
        self.assertEqual(assessment.reason, "heterogeneous_taxonomy")
        self.assertEqual(decision.route, "sol_low")

    def test_missing_candidate_or_master_code_is_not_conclusive(self):
        insufficient = assess_candidate_taxonomy(
            [{"master_code": "38_02_02"}, {"master_code": "38_02_02"}]
        )
        missing_code = assess_candidate_taxonomy(
            [
                {"master_code": "38_02_02"},
                {"master_code": None},
                {"master_code": "38_02_02"},
            ]
        )

        self.assertEqual(insufficient.reason, "insufficient_candidates")
        self.assertEqual(missing_code.reason, "missing_taxonomy")

    def test_normalized_exact_stays_on_deterministic_path(self):
        proposals = [
            {"master_code": "38_02_02", "exact_match": rank == 1}
            for rank in range(1, 4)
        ]

        decision = decide_bs25ai_route(proposals)

        self.assertEqual(decision.route, "exact")
        self.assertIsNone(decision.flag)


class CodexSelectionTests(unittest.TestCase):
    def test_operator_can_select_a_bs25_proposal(self):
        selection = resolve_codex_selection(2, False)

        self.assertEqual(selection.kind, "proposal")
        self.assertEqual(selection.proposal_rank, 2)

    def test_operator_can_clear_the_draft(self):
        selection = resolve_codex_selection(None, True)

        self.assertEqual(selection.kind, "clear")
        self.assertIsNone(selection.master_code)

    def test_selection_rejects_ambiguous_or_invalid_actions(self):
        with self.assertRaisesRegex(ValueError, "una sola scelta"):
            resolve_codex_selection(1, True)
        with self.assertRaisesRegex(ValueError, "una sola scelta"):
            resolve_codex_selection(None, False)


if __name__ == "__main__":
    unittest.main()
