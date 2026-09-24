"""Agent-facing policy authoring tools. The customer confirms in the app."""

from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from leash.contracts import PurchaseFacts

from .store import (
    BOOLEAN_STRING_FIELDS, CURRENCIES, EXAMPLE_ACTIONS, FIELDS,
    NUMBER_FIELDS, OPERATORS, RULE_KEYS, DraftConflict, DraftStore, InvalidDraft,
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


PARKED_MESSAGE = "purchases arrive through the simulator in demo mode; see plan 01 step 12"


class PurchasesParked(ToolError, NotImplementedError):
    """`buy` and `get_purchase_status` are declared but parked until after the submission."""


class DraftNotFound(ToolError):
    """The agent asked about a draft the store does not hold."""


def policy_status(store: DraftStore, draft_id: str) -> dict[str, Any]:
    """Read-only state of one draft. Never writes, never confirms."""
    state = store.decision_state(draft_id)
    if state == "confirmed":
        confirmation = store.get_confirmation(draft_id)
        return {
            "draft_id": draft_id,
            "version": confirmation["version"],
            "status": "confirmed",
            "mandate_id": confirmation["mandate_id"],
            "confirmed_at": confirmation["confirmed_at"],
            "rejected_reason": None,
        }
    if state == "rejected":
        rejection = store.get_rejection(draft_id)
        return {
            "draft_id": draft_id,
            "version": rejection["version"],
            "status": "rejected",
            "mandate_id": None,
            "confirmed_at": None,
            "rejected_reason": rejection["reason"],
        }
    return {
        "draft_id": draft_id,
        "version": store.get(draft_id)["version"],
        "status": "pending",
        "mandate_id": None,
        "confirmed_at": None,
        "rejected_reason": None,
    }


def policy_summary(store: DraftStore, draft_id: str) -> dict[str, Any]:
    """The customer-facing read-back of the current version. No rule fields, no hash."""
    draft = store.get(draft_id)
    return {
        "draft_id": draft["draft_id"],
        "version": draft["version"],
        "instruction": draft["instruction"],
        "plain_english": [rule["plain_english"] for rule in draft["rules"]],
        "examples": [
            {"description": e["description"], "expected": e["expected"], "why": e["why"]}
            for e in draft["examples"]
        ],
        "open_questions": [
            {"question": q["question"], "options": q["options"], "answer": q["answer"]}
            for q in draft["open_questions"]
        ],
        "uncertainty_policy": draft["uncertainty_policy"],
    }


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item_id: Annotated[str, Field(min_length=1)]
    item_name: Annotated[str, Field(min_length=1)]
    item_category: Annotated[str, Field(min_length=1)]
    item_details: str
    unit_price_chf: Annotated[float, Field(gt=0)]
    quantity: Annotated[int, Field(ge=1)]


class CartMerchant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    merchant_id: Annotated[str, Field(min_length=1)]
    merchant_name: Annotated[str, Field(min_length=1)]
    merchant_category: Annotated[str, Field(min_length=1)]
    merchant_mcc: Annotated[str, Field(pattern=r"^[0-9]{4}$")]
    merchant_country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class BearerAuth:
    """ASGI middleware: every HTTP request needs `Authorization: Bearer <token>`, else 401."""

    def __init__(self, app: ASGIApp, token: str):
        if not token:
            raise RuntimeError("bearer token is empty")
        self.app = app
        self.expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            supplied = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                body = b'{"error":"unauthorized","detail":"Authorization: Bearer token required"}'
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b"Bearer"),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


class PolicyMCPServer(MCPServer):
    """MCPServer whose streamable-http app only answers holders of the shared bearer token."""

    bearer_token: str | None = None

    def streamable_http_app(self, **kwargs: Any):  # type: ignore[override]
        if not self.bearer_token:
            raise RuntimeError("the streamable-http transport needs LEASH_MCP_TOKEN")
        return BearerAuth(super().streamable_http_app(**kwargs), self.bearer_token)


def create_server(store: DraftStore, bearer_token: str | None = None) -> PolicyMCPServer:
    server = PolicyMCPServer("Leash Policy Authoring")
    server.bearer_token = bearer_token

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
        try:
            return submit_policy_proposal(store, instruction, proposal)
        except InvalidDraft as exc:
            raise ToolError(f"InvalidDraft: {exc}") from exc

    def _known(draft_id: str) -> None:
        try:
            store.get(draft_id)
        except KeyError as exc:
            raise DraftNotFound(f"unknown draft_id: {draft_id}") from exc
        except (InvalidDraft, DraftConflict) as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    @server.tool()
    def get_policy_status(draft_id: str) -> dict[str, Any]:
        """Poll a proposed draft: pending, confirmed with the mandate_id, or rejected with the reason.

        Read-only. Confirmation happens only in the customer's Wallet.
        """
        _known(draft_id)
        return policy_status(store, draft_id)

    @server.tool()
    def get_policy_summary(draft_id: str) -> dict[str, Any]:
        """Read back the plain-English rules, examples, open questions and uncertainty setting of a draft."""
        _known(draft_id)
        return policy_summary(store, draft_id)

    @server.tool()
    def buy(
        mandate_id: str, cart: list[CartLine], merchant: CartMerchant, facts: list[PurchaseFacts]
    ) -> dict[str, Any]:
        """Ask for a purchase decision under a confirmed mandate. Parked: purchases arrive through the simulator."""
        raise PurchasesParked(PARKED_MESSAGE)

    @server.tool()
    def get_purchase_status(authorization_id: str) -> dict[str, Any]:
        """Read the decision and step-up resolution of one purchase. Parked with buy."""
        raise PurchasesParked(PARKED_MESSAGE)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m leash.policy.mcp_server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)

    root = os.environ.get("LEASH_POLICY_STORE")
    if not root:
        raise RuntimeError("LEASH_POLICY_STORE is required for the policy MCP server")
    store = DraftStore(Path(root))

    if args.transport == "stdio":
        if args.port is not None:
            raise RuntimeError("--port only applies to --transport streamable-http")
        create_server(store).run(transport="stdio")
        return

    if args.port is None:
        raise RuntimeError("--transport streamable-http requires --port")
    token = os.environ.get("LEASH_MCP_TOKEN")
    if not token:
        raise RuntimeError("LEASH_MCP_TOKEN is required for --transport streamable-http")
    create_server(store, bearer_token=token).run(
        transport="streamable-http", host=args.host, port=args.port
    )


if __name__ == "__main__":
    main()
