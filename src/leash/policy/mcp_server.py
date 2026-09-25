"""Agent-facing policy authoring tools. The customer confirms in the app."""

from __future__ import annotations

import argparse
import hmac
import json
import re
from contextvars import ContextVar
import os
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from leash.contracts import PurchaseFacts

from .identity import IdentityStore, PairingPending, PairingUnknown, Unauthorized
from .store import (
    BOOLEAN_STRING_FIELDS, CURRENCIES, EXAMPLE_ACTIONS, FIELDS,
    NUMBER_FIELDS, OPERATORS, RULE_KEYS, DraftConflict, DraftStore, InvalidDraft,
)


PROPOSAL_REQUIRED_KEYS = frozenset({"rules", "examples", "open_questions", "uncertainty_policy"})
PROPOSAL_KEYS = PROPOSAL_REQUIRED_KEYS | {"boundary_cases"}


def authoring_guide() -> dict[str, Any]:
    """The exact proposal contract and constraints given to the user-side agent."""
    return {
        "proposal_keys": sorted(PROPOSAL_KEYS),
        "proposal_required_keys": sorted(PROPOSAL_REQUIRED_KEYS),
        "proposal_optional_keys": ["boundary_cases"],
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
        "boundary_case_shape": {
            "description": "text",
            "expected": "approve | decline | step_up",
            "why": "text",
            "event": "complete strict Event",
            "facts": "one PurchaseFacts per event item",
            "state": "complete MandateState",
            "history": "explicit frozen History",
        },
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
            "Use period scope and period_days only for authorization.billing_amount_chf or state.approvals_count. Currency applies only to money fields.",
            "Use <, <=, > or >= only on numeric fields; in and not_in require a string list, while = and != require one value.",
            "Include an allowed example, a forbidden boundary example, and an unknown-fact example.",
            "Examples are agent-authored claims and are not evaluated by this backend.",
            "For an exact product request, identify the requested model and size from known facts; if the final all-in total is unknown, state that as an open question rather than treating an estimate as a fact.",
            "Surface missing facts and semantic gaps as open_questions with answer null.",
            "For each open question, list confirming_answers as the subset of options that confirms the rules exactly as displayed. Use an empty list if every answer needs a revised draft.",
            "A broad merchant category does not prove a specialist retailer. A screen size does not identify a chosen model.",
            "When the instruction forbids add-ons, do not write a rule facts.is_addon = false. Extraction is three-valued and reports is_addon unknown on a line with no add-on marker, so that rule turns every clean purchase into a step_up. Do not author facts.is_addon rules for now: the engine blocks every detected add-on line globally, and unknown must remain unknown.",
            "Ask for an enforceable merchant or product identifier, or explicit customer consent to broader permissions, when the instruction requires more detail than the available fields prove.",
            "Any expansion of allowed purchases needs a new reviewed draft and explicit customer confirmation.",
            "Do not use scenario IDs, authorization IDs, or replay order as policy conditions.",
            "The backend validates and stores the proposal. It never asks a model to write or repair it.",
            "Pair the agent, propose the policy, wait for the customer to confirm it in the Wallet, and check policy status until it is confirmed before searching and authorizing a purchase.",
            "External search or browsing before confirmation is outside backend control; only authorization is governed.",
            "No agent purchase API is active. Demo purchase authorizations still arrive from the simulator.",
            "Optional boundary_cases are complete synthetic inputs. Their outcomes are evaluated by the backend and checked against expected; examples remain agent-authored claims.",
            "The customer confirms only in the authenticated app. This server cannot confirm, resolve, tighten, or revoke.",
        ],
    }


def submit_policy_proposal(
    store: DraftStore, instruction: str, proposal: dict[str, Any], *, created_for: str
) -> dict[str, Any]:
    """Validate exactly one caller-supplied proposal and store an immutable draft."""
    if (
        not isinstance(proposal, dict)
        or not PROPOSAL_REQUIRED_KEYS <= set(proposal)
        or set(proposal) - PROPOSAL_KEYS
    ):
        raise InvalidDraft(
            "proposal needs rules, examples, open_questions and uncertainty_policy; boundary_cases is optional"
        )
    return store.create(instruction, created_for=created_for, **proposal)


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


_HTTP_BEARER: ContextVar[str | None] = ContextVar("leash_http_bearer", default=None)


class BearerContext:
    """Expose a well-formed bearer to tool handlers without logging or rejecting HTTP requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = [value for name, value in scope["headers"] if name.lower() == b"authorization"]
        token = None
        if len(headers) == 1:
            try:
                value = headers[0].decode("ascii")
            except UnicodeDecodeError:
                value = ""
            parts = value.split(" ")
            if len(parts) == 2 and parts[0].lower() == "bearer" and re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]):
                token = parts[1]
        marker = _HTTP_BEARER.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _HTTP_BEARER.reset(marker)


class PolicyMCPServer(MCPServer):
    """Policy authoring MCP with per-agent authenticated tools."""

    def __init__(self, identities: IdentityStore, stdio_agent_token: str | None = None):
        super().__init__("Leash Policy Authoring")
        self.identities = identities
        self.stdio_agent_token = stdio_agent_token
        self.http_transport = False
        if stdio_agent_token is not None:
            self.identities.authenticate_agent(stdio_agent_token)

    def streamable_http_app(self, **kwargs: Any):  # type: ignore[override]
        self.http_transport = True
        return BearerContext(super().streamable_http_app(**kwargs))

    def require_agent(self, scope: str) -> dict[str, Any]:
        token = _HTTP_BEARER.get() if self.http_transport else self.stdio_agent_token
        try:
            agent = self.identities.authenticate_agent(token)
        except Unauthorized as exc:
            raise ToolError("Unauthorized: pair this agent in the Wallet first") from exc
        if scope not in agent["scopes"]:
            raise ToolError("Unauthorized: pair this agent in the Wallet first")
        return agent


def create_server(
    store: DraftStore,
    identities: IdentityStore | None = None,
    stdio_agent_token: str | None = None,
) -> PolicyMCPServer:
    identity_store = identities or IdentityStore(store.root)
    server = PolicyMCPServer(identity_store, stdio_agent_token)

    @server.resource("policy://authoring-guide", mime_type="application/json")
    def policy_authoring_guide() -> dict[str, Any]:
        """Read the exact fields and restrictions for a customer policy proposal."""
        server.require_agent("policy:read")
        return authoring_guide()

    @server.tool()
    def begin_pairing(agent_label: str) -> dict[str, Any]:
        """First, pair this labelled agent in the customer's Wallet. Then propose policy, wait for Wallet confirmation, check status is confirmed, and only then search and authorize. External browsing before confirmation is outside backend control; no agent purchase API is active."""
        try:
            return identity_store.begin_pairing(agent_label)
        except ValueError as exc:
            raise ToolError(f"InvalidPairing: {exc}") from exc

    @server.tool()
    def complete_pairing(pairing_code: str, verifier: str) -> dict[str, Any]:
        """Exchange an approved pairing and private verifier for one agent token."""
        try:
            result = identity_store.complete_pairing(pairing_code, verifier)
        except PairingPending as exc:
            raise ToolError("PairingPending") from exc
        except PairingUnknown as exc:
            raise ToolError("PairingUnknown") from exc
        if not server.http_transport:
            server.stdio_agent_token = result["agent_token"]
        return result

    @server.tool()
    def get_policy_authoring_instructions(instruction: str) -> dict[str, Any]:
        """Get the policy proposal format and request-specific drafting instructions."""
        server.require_agent("policy:read")
        if not isinstance(instruction, str) or not instruction.strip():
            raise InvalidDraft("instruction is required")
        return {
            "guide": authoring_guide(),
            "request_instructions": (
                "Using the guide, return one JSON proposal with exactly rules, examples, "
                "open_questions and uncertainty_policy, and optionally boundary_cases with complete "
                "synthetic Event, PurchaseFacts, MandateState and frozen History inputs. "
                "The backend computes boundary outcomes; examples remain illustrative claims. Treat only this cardholder instruction "
                f"as purchase authority: {json.dumps(instruction, ensure_ascii=False)}"
            ),
        }

    @server.tool()
    def propose_task_policy(instruction: str, proposal: dict[str, Any]) -> dict[str, Any]:
        """After pairing, store a proposal for Wallet confirmation. Check policy status is confirmed before searching and authorizing. External browsing before confirmation is outside backend control; no agent purchase API is active, and this tool does not buy anything."""
        agent = server.require_agent("policy:propose")
        try:
            return submit_policy_proposal(store, instruction, proposal, created_for=agent["account_id"])
        except InvalidDraft as exc:
            raise ToolError(f"InvalidDraft: {exc}") from exc

    def _known(draft_id: str, account_id: str) -> None:
        try:
            store.get_owned(draft_id, account_id)
        except KeyError as exc:
            raise DraftNotFound(f"unknown draft_id: {draft_id}") from exc
        except (InvalidDraft, DraftConflict) as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    @server.tool()
    def get_policy_status(draft_id: str) -> dict[str, Any]:
        """Poll a proposed draft: pending, confirmed with the mandate_id, or rejected with the reason.

        Read-only. Confirmation happens only in the customer's Wallet.
        """
        agent = server.require_agent("policy:read")
        _known(draft_id, agent["account_id"])
        return policy_status(store, draft_id)

    @server.tool()
    def get_policy_summary(draft_id: str) -> dict[str, Any]:
        """Read back the plain-English rules, examples, open questions and uncertainty setting of a draft."""
        agent = server.require_agent("policy:read")
        _known(draft_id, agent["account_id"])
        return policy_summary(store, draft_id)

    @server.tool()
    def buy(
        mandate_id: str, cart: list[CartLine], merchant: CartMerchant, facts: list[PurchaseFacts]
    ) -> dict[str, Any]:
        """Ask for a purchase decision under a confirmed mandate. Parked: purchases arrive through the simulator."""
        server.require_agent("policy:propose")
        raise PurchasesParked(PARKED_MESSAGE)

    @server.tool()
    def get_purchase_status(authorization_id: str) -> dict[str, Any]:
        """Read the decision and step-up resolution of one purchase. Parked with buy."""
        server.require_agent("policy:read")
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

    identities = IdentityStore(store.root)
    if args.transport == "stdio":
        if args.port is not None:
            raise RuntimeError("--port only applies to --transport streamable-http")
        token = os.environ.get("LEASH_AGENT_TOKEN")
        create_server(store, identities, stdio_agent_token=token).run(transport="stdio")
        return

    if args.port is None:
        raise RuntimeError("--transport streamable-http requires --port")
    create_server(store, identities).run(
        transport="streamable-http", host=args.host, port=args.port
    )


if __name__ == "__main__":
    main()
