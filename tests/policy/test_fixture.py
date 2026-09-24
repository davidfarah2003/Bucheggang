"""Contract checks for the draft consumed by the customer app."""

import hashlib
import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "scen0002_draft.json"


class FixtureTests(unittest.TestCase):
    def test_draft_can_be_verified_independently(self):
        draft = json.loads(FIXTURE.read_text())
        canonical = {
            "instruction": draft["instruction"],
            "rules": draft["rules"],
            "uncertainty_policy": draft["uncertainty_policy"],
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        self.assertEqual(draft["hash"], digest)
        self.assertEqual(draft["version"], 1)
        self.assertEqual(draft["uncertainty_policy"], "ask")

        for rule in draft["rules"]:
            with self.subTest(field=rule["field"]):
                self.assertIn(rule["source_text"], draft["instruction"])
                self.assertTrue(rule["plain_english"])

        outcomes = {example["expected"] for example in draft["examples"]}
        self.assertEqual(outcomes, {"approve", "decline", "step_up"})
        self.assertTrue(draft["open_questions"])


if __name__ == "__main__":
    unittest.main()
