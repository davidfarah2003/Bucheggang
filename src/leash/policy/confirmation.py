"""Customer-only confirmation of an immutable policy draft."""

from __future__ import annotations

from typing import Any, Protocol

from .store import DraftConflict, DraftStore, InvalidDraft


class MandateClient(Protocol):
    def create(self, draft: dict[str, Any], global_rules: list[dict[str, Any]]) -> str: ...

    def confirm(self, simulator_draft_id: str) -> str: ...


class UnresolvedQuestion(InvalidDraft):
    """A selected answer has no executable policy meaning."""


def _answered_draft(
    store: DraftStore,
    draft_id: str,
    version: int,
    hash_value: str,
    answers: dict[str, str],
) -> dict[str, Any]:
    draft = store.assert_current(draft_id, version, hash_value)
    questions = draft["open_questions"]
    expected = [question["question"] for question in questions]
    if len(expected) != len(set(expected)):
        raise UnresolvedQuestion("draft contains duplicate open questions")
    if set(answers) != set(expected):
        raise UnresolvedQuestion("every open question needs exactly one customer answer")

    policy = draft["uncertainty_policy"]
    answered = []
    for question in questions:
        answer = answers[question["question"]]
        if answer not in question["options"]:
            raise UnresolvedQuestion(f"answer is not an option: {question['question']}")
        if answer not in question["confirming_answers"]:
            raise UnresolvedQuestion(
                f"question needs a revised executable policy before confirmation: {question['question']}"
            )
        if answer in {"ask", "decline"} and set(question["options"]) - {"ask", "decline"}:
            raise UnresolvedQuestion("an uncertainty answer cannot resolve a semantic question")
        if answer == "ask" and policy == "decline":
            raise UnresolvedQuestion("ask would expand a decline policy; revise and review the draft first")
        if answer in {"ask", "decline"} and (policy == "approve" or answer == "decline"):
            policy = answer
        answered.append({**question, "answer": answer})

    if questions:
        return store.revise(
            draft_id,
            expected_version=version,
            expected_hash=hash_value,
            uncertainty_policy=policy,
            open_questions=answered,
        )
    return draft


def confirm_policy(
    store: DraftStore,
    mandates: MandateClient,
    draft_id: str,
    *,
    version: int,
    hash_value: str,
    answers: dict[str, str],
    confirmed_by: str,
    global_policy: dict[str, Any],
) -> dict[str, Any]:
    """Create and confirm a simulator mandate after an authenticated app action.

    The caller authenticates the customer and supplies its identity. No agent
    interface imports this function.
    """
    if not confirmed_by:
        raise InvalidDraft("authenticated customer identity is required")
    draft = _answered_draft(store, draft_id, version, hash_value, answers)
    boundary_results = store.reevaluate_boundary_cases_for_confirmation(
        draft_id, version=draft["version"], hash_value=draft["hash"]
    )
    attempt_id = store.begin_confirmation(
        draft_id,
        version=draft["version"],
        hash_value=draft["hash"],
        confirmed_by=confirmed_by,
    )
    global_rules = global_policy["rules"]
    simulator_draft_id = mandates.create(draft, global_rules)
    store.record_simulator_draft(
        draft_id,
        version=draft["version"],
        hash_value=draft["hash"],
        attempt_id=attempt_id,
        simulator_draft_id=simulator_draft_id,
    )
    mandate_id = mandates.confirm(simulator_draft_id)
    result = store.record_confirmation(
        draft_id,
        version=draft["version"],
        hash_value=draft["hash"],
        simulator_draft_id=simulator_draft_id,
        mandate_id=mandate_id,
        confirmed_by=confirmed_by,
        attempt_id=attempt_id,
        global_version=global_policy["version"],
        global_hash=global_policy["hash"],
        global_rules=global_rules,
        boundary_results=boundary_results,
    )
    from .purchases import demo_identity, write_identity

    identity = demo_identity()
    if identity is not None:
        write_identity(store, draft_id, identity, source="demo_card")
    return {
        "mandate_id": mandate_id,
        "draft_id": draft_id,
        "version": draft["version"],
        "hash": draft["hash"],
        "status": "active",
        "confirmed_at": result["confirmation"]["confirmed_at"],
        "global_policy_version": result["confirmation"]["global_version"],
        "global_policy_hash": result["confirmation"]["global_hash"],
    }
