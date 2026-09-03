import unittest

from codex_app_server import CodexAppServer, _notification_turn_id
from prompts import RESULT_SCHEMA, build_goal, build_prompt


class CodexAppServerProtocolTests(unittest.TestCase):
    def test_request_preserves_notifications_arriving_before_response(self):
        client = CodexAppServer(timeout_seconds=1)
        client._write = lambda message: None
        client._messages.put(
            {"method": "item/completed", "params": {"turnId": "turn-1"}}
        )
        client._messages.put({"id": 1, "result": {"ok": True}})

        response = client.request("test", {})

        self.assertEqual(response, {"ok": True})
        self.assertEqual(client._next_message(999999999)["method"], "item/completed")

    def test_goal_is_item_scoped_and_non_final(self):
        goal = build_goal({"company_item_code": "HERAEUS|66101150"})

        self.assertIn("HERAEUS|66101150", goal)
        self.assertIn("non definitiva", goal)
        self.assertIn("match, ambiguous o unresolved", goal)

    def test_xhigh_prompt_requires_web_components_and_canonical_reference(self):
        prompt = build_prompt(
            "xhigh",
            __import__("pathlib").Path("/tmp/case.json"),
            __import__("pathlib").Path("/tmp/bundle"),
            __import__("pathlib").Path("/tmp/master_codes.json"),
        )

        self.assertIn("ricerca web completa", prompt)
        self.assertIn("manufacturer, brand/family, pack, feature, measure", prompt)
        self.assertIn("fuori dalla Top-3", prompt)
        self.assertFalse(RESULT_SCHEMA.get("additionalProperties", True))

    def test_notification_turn_id_supports_item_and_turn_shapes(self):
        self.assertEqual(
            _notification_turn_id("item/completed", {"turnId": "turn-1"}),
            "turn-1",
        )
        self.assertEqual(
            _notification_turn_id(
                "turn/completed", {"turn": {"id": "turn-2", "status": "completed"}}
            ),
            "turn-2",
        )


if __name__ == "__main__":
    unittest.main()
