"""Draft version, hash and simulator-boundary tests."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from leash.policy import DraftConflict, DraftStore, InvalidDraft, simulator_payload  # noqa: E402


INSTRUCTION = "Buy one grocery item for CHF 20 or less. Ask me when uncertain."
RULE = {
    "field": "authorization.billing_amount_chf",
    "operator": "<=",
    "value": 20,
    "currency": "CHF",
    "scope": "purchase",
    "source_text": "CHF 20 or less",
    "plain_english": "Spend no more than CHF 20.",
}


class DraftStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DraftStore(self.directory.name)

    def test_stale_confirmation_and_original_version_immutability(self):
        first = self.store.create(INSTRUCTION, [RULE])
        second = self.store.revise(
            first["draft_id"],
            expected_version=first["version"],
            expected_hash=first["hash"],
            uncertainty_policy="decline",
        )
        self.assertEqual(second["version"], 2)
        self.assertNotEqual(second["hash"], first["hash"])
        with self.assertRaises(DraftConflict):
            self.store.record_confirmation(
                first["draft_id"],
                version=first["version"],
                hash_value=first["hash"],
                mandate_id="TM-1",
                confirmed_by="customer",
            )
        old_file = Path(self.directory.name) / first["draft_id"] / "v1.json"
        self.assertEqual(json.loads(old_file.read_text()), first)
        confirmed = self.store.record_confirmation(
            second["draft_id"],
            version=second["version"],
            hash_value=second["hash"],
            mandate_id="TM-2",
            confirmed_by="customer",
        )
        self.assertEqual(confirmed["confirmation"]["mandate_id"], "TM-2")

    def test_modified_stored_rule_is_detected(self):
        draft = self.store.create(INSTRUCTION, [RULE])
        path = Path(self.directory.name) / draft["draft_id"] / "v1.json"
        changed = json.loads(path.read_text())
        changed["rules"][0]["value"] = 200
        path.write_text(json.dumps(changed))
        with self.assertRaises(DraftConflict):
            self.store.get(draft["draft_id"])

    def test_agent_rule_metadata_does_not_reach_simulator(self):
        draft = self.store.create(INSTRUCTION, [RULE])
        payload = simulator_payload(draft)
        self.assertEqual(payload["hard_rules"][0]["value"], 20)
        self.assertNotIn("source_text", payload["hard_rules"][0])
        self.assertNotIn("plain_english", payload["hard_rules"][0])
        self.assertEqual(payload["instruction"], INSTRUCTION)

    def test_unknown_fields_and_boolean_values_are_refused(self):
        with self.assertRaises(InvalidDraft):
            self.store.create(INSTRUCTION, [{**RULE, "dangerous_override": True}])
        with self.assertRaises(InvalidDraft):
            self.store.create(INSTRUCTION, [{**RULE, "value": True}])

    def test_rejected_draft_cannot_be_confirmed(self):
        draft = self.store.create(INSTRUCTION, [RULE])
        self.store.reject(
            draft["draft_id"],
            version=draft["version"],
            hash_value=draft["hash"],
            rejected_by="customer",
            reason="Please change the price limit",
        )
        with self.assertRaises(DraftConflict):
            self.store.record_confirmation(
                draft["draft_id"],
                version=draft["version"],
                hash_value=draft["hash"],
                mandate_id="TM-3",
                confirmed_by="customer",
            )

    def test_caller_mutation_cannot_change_stored_rule(self):
        proposed = [{**RULE}]
        draft = self.store.create(INSTRUCTION, proposed)
        proposed[0]["value"] = 200
        self.assertEqual(self.store.get(draft["draft_id"])["rules"][0]["value"], 20)


if __name__ == "__main__":
    unittest.main()
