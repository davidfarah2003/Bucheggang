"""Agent-facing policy authoring tools. The customer confirms in the app."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from .store import (
    BOOLEAN_STRING_FIELDS, CURRENCIES, EXAMPLE_ACTIONS, FIELDS,
    NUMBER_FIELDS, OPERATORS, RULE_KEYS, DraftStore, InvalidDraft,
)


PROPOSAL_KEYS = frozenset({"rules", "examples", "open_questions", "uncertainty_policy"})


def authoring_guide() -> dict[str, Any]:
    """The exact proposal contract and constraints given to the user-side agent."""
    return {
        "proposal_keys": sorted(PROPOSAL_KEYS),
        "rule_keys": sorted(RULE_KEYS),
        "fields": sorted(FIELDS),
        "numeric_fields": sorted(NUMBER_FIELDS),
        "boolean_string_fields": sorted(BOOLEAN_STRING_FIELDS),
        "operators": sorted(OPERATORS),
        "currencies": sorted(CURRENCIES),
        "uncertainty_policies": ["ask", "decline", "approve"],
        "example_actions": sorted(EXAMPLE_ACTIONS),
        "rule_shape": {
            "field": "one field from fields",
            "operator": "one operator from operators",
            "value": "finite number, nonempty string, or nonempty list of strings",
            "source_text": "exact nonempty substring of the cardholder instruction",
            "plain_english": "nonempty sentence for the customer",
            "currency": "optional, one currency from currencies",
            "scope": "optional purchase or period",
            "period_days": "required positive integer when scope is period",
        },
        "example_shape": {"description": "text", "expected": "approve | decline | step_up", "why": "text"},
        "question_shape": {
            "question": "text",
            "options": ["option 1", "option 2"],
            "confirming_answers": ["option 1"],
            "answer": None,
        },
        "instructions": [
            "Treat the cardholder instruction as the sole source of purchase permission.",
            "Support any shopping category. Never assume the request is for clothing or another predefined product type.",
            "Use an exact source_text substring for every rule. Do not invent a condition or permission.",
            "Use finite numbers for numeric fields. Boolean and history fields use the strings true and false. Other fields use strings or lists of strings.",
            "Use period scope and period_days only for a supported cumulative numeric rule.",
            "Include an allowed example, a forbidden boundary example, and an unknown-fact example.",
            "Surface missing facts and semantic gaps as open_questions with answer null.",
            "For each open question, list confirming_answers as the subset of options that confirms the rules exactly as displayed. Use an empty list if every answer needs a revised draft.",
            "A broad merchant category does not prove a specialist retailer. A screen size does not identify a chosen model.",
            "Ask for an enforceable merchant or product identifier, or explicit customer consent to broader permissions, when the instruction requires more detail than the available fields prove.",
            "Any expansion of allowed purchases needs a new reviewed draft and explicit customer confirmation.",
            "Do not use scenario IDs, authorization IDs, or replay order as policy conditions.",
            "The backend validates and stores the proposal. It never asks a model to write or repair it.",
            "The customer confirms only in the authenticated app. This server cannot confirm, resolve, tighten, or revoke.",
        ],
    }


def submit_policy_proposal(
    store: DraftStore, instruction: str, proposal: dict[str, Any]
) -> dict[str, Any]:
    """Validate exactly one caller-supplied proposal and store an immutable draft."""
    if not isinstance(proposal, dict) or set(proposal) != PROPOSAL_KEYS:
        raise InvalidDraft("proposal must contain exactly rules, examples, open_questions and uncertainty_policy")
    return store.create(instruction, **proposal)


def create_server(store: DraftStore) -> MCPServer:
    server = MCPServer("Leash Policy Authoring")

    @server.resource("policy://authoring-guide", mime_type="application/json")
    def policy_authoring_guide() -> dict[str, Any]:
        """Read the exact fields and restrictions for a customer policy proposal."""
        return authoring_guide()

    @server.tool()
    def get_policy_authoring_instructions(instruction: str) -> dict[str, Any]:
        """Get the policy proposal format and request-specific drafting instructions."""
        if not isinstance(instruction, str) or not instruction.strip():
            raise InvalidDraft("instruction is required")
        return {
            "guide": authoring_guide(),
            "request_instructions": (
                "Using the guide, return one JSON proposal with exactly rules, examples, "
                "open_questions and uncertainty_policy. Treat only this cardholder instruction "
                f"as purchase authority: {json.dumps(instruction, ensure_ascii=False)}"
            ),
        }

    @server.tool()
    def propose_task_policy(instruction: str, proposal: dict[str, Any]) -> dict[str, Any]:
        """Validate and store a policy JSON proposed by the calling agent for app review."""
        return submit_policy_proposal(store, instruction, proposal)

    return server


def main() -> None:
    root = os.environ.get("LEASH_POLICY_STORE")
    if not root:
        raise RuntimeError("LEASH_POLICY_STORE is required for the policy MCP server")
    create_server(DraftStore(Path(root))).run(transport="stdio")


if __name__ == "__main__":
    main()
