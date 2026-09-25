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
from urllib.parse import quote

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from leash.api.main import _validate_origin
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


SERVER_INSTRUCTIONS = """Leash is the customer's Wallet control layer. You are a shopping agent; the customer gives you a sentence of instructions, you turn it into a policy proposal, the customer confirms it in their Wallet, and only a confirmed mandate lets any purchase be judged. You never confirm, tighten or revoke anything yourself, and you never answer a step-up on the customer's behalf.

Keep it smooth for the customer. They should type one sentence, tap Approve once for pairing, and tap Confirm once in the Wallet. Everything else is your job:

- Do not ask the customer questions in chat that the guide lets you encode as a rule or as an open question in the draft. The Wallet shows open questions with their options, so the customer answers them where they confirm.
- Shape the policy to the request. A recurring errand ("weekly groceries", "order our household basics") gets a per-order cap, a period cap with period_days, the merchant category and the item category, and no purchase-count rule. A one-off purchase ("buy the monitor I chose", "one grocery item") gets a per-order cap, items.count = 1, state.approvals_count < 1 so the mandate is spent after one approval, and, for an exact item, facts.product_type equal to the customer's own wording plus an open question naming the exact model.
- Encode only what the customer said. "Shops I use" becomes history.merchant_seen_on_card = true; "ask me when unsure" becomes uncertainty_policy ask; "never buy anything else" becomes items.count or items.category, never a guess at a brand.
- Prefer one to three open questions with two or three short options each. A question is for a real ambiguity (which model, does household include toiletries), not for something the sentence already settles.
- Write plain_english as the sentence a person would read on a phone: what is allowed, in their words, one clause each.
- After proposing, tell the customer in one line that the policy is waiting in their Wallet and what it allows. Then poll; do not re-propose while the draft is pending.

Run the flow in this order, one tool per step:

1. begin_pairing(agent_label) once per session. Give the customer only wallet_url. Keep verifier private; never print it, log it or put it in a URL.
2. When the customer says they approved you in the Wallet, complete_pairing(pairing_code, verifier). The token stays inside this server process.
3. get_policy_authoring_instructions(instruction) with the customer's sentence verbatim. Read the returned guide: it lists every allowed field and operator.
4. propose_task_policy(instruction, proposal). Every rule quotes an exact substring of the instruction as source_text. Do not invent permissions the customer did not state; put anything unclear in open_questions.
5. Tell the customer the draft is waiting in their Wallet (it opens at <wallet origin>/app/?draft_id=<draft_id>), then poll get_policy_status(draft_id) until state is confirmed (you receive mandate_id) or rejected (you receive the reason and draft a new proposal).
6. Only after confirmed: search for the product. Purchases are judged by the Wallet against the mandate; buy and get_purchase_status are parked in the demo, where purchase attempts arrive from the organizer's simulator.

Worked example. Instruction: "Do the weekly grocery shopping online at supermarkets I already use. Never spend more than CHF 100 per order or CHF 250 in any 7-day window; groceries and household basics only. If unsure, ask."

proposal = {
  "rules": [
    {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 100, "currency": "CHF", "scope": "purchase",
     "source_text": "CHF 100 per order", "plain_english": "Each order including delivery must cost CHF 100 or less."},
    {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 250, "currency": "CHF", "scope": "period", "period_days": 7,
     "source_text": "CHF 250 in any 7-day window", "plain_english": "Approved purchases plus this order must total CHF 250 or less over seven days."},
    {"field": "authorization.channel", "operator": "=", "value": "ecommerce", "scope": "purchase",
     "source_text": "shopping online", "plain_english": "Use the ecommerce channel."},
    {"field": "authorization.merchant.merchant_category", "operator": "=", "value": "groceries", "scope": "purchase",
     "source_text": "supermarkets", "plain_english": "Use a grocery retailer."},
    {"field": "items.category", "operator": "=", "value": "groceries", "scope": "purchase",
     "source_text": "groceries and household basics only", "plain_english": "Every basket line must be a grocery item."},
    {"field": "history.merchant_seen_on_card", "operator": "=", "value": "true", "scope": "purchase",
     "source_text": "I already use", "plain_english": "Require a prior approved purchase at this shop on this card."}
  ],
  "examples": [
    {"description": "CHF 84 order at Coop, bought there before", "expected": "approve", "why": "under both limits, known shop, groceries"},
    {"description": "CHF 120 order at Migros", "expected": "decline", "why": "over the CHF 100 per-order limit"}
  ],
  "open_questions": [
    {"question": "Do household basics include cleaning products and toiletries?",
     "options": ["Yes, include them", "No, food only"], "confirming_answers": ["Yes, include them", "No, food only"], "answer": null}
  ],
  "uncertainty_policy": "ask"
}

Second example, a one-off exact item. Instruction: "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. Do not add anything I did not ask for. Ask me when uncertain."

proposal = {
  "rules": [
    {"field": "authorization.billing_amount_chf", "operator": "<=", "value": 400, "currency": "CHF", "scope": "purchase",
     "source_text": "CHF 400 or less", "plain_english": "The order including delivery must cost CHF 400 or less."},
    {"field": "facts.product_type", "operator": "=", "value": "27-inch monitor", "scope": "purchase",
     "source_text": "27-inch monitor", "plain_english": "The item must be the 27-inch monitor you chose."},
    {"field": "items.count", "operator": "=", "value": 1, "scope": "purchase",
     "source_text": "Do not add anything I did not ask for", "plain_english": "The cart holds exactly one line."},
    {"field": "history.merchant_seen_on_card", "operator": "=", "value": "true", "scope": "purchase",
     "source_text": "a seller I have bought from before", "plain_english": "The seller must already have an approved purchase on this card."},
    {"field": "state.approvals_count", "operator": "<", "value": 1, "scope": "purchase",
     "source_text": "Buy the 27-inch monitor I chose", "plain_english": "One approved purchase ends this permission."}
  ],
  "examples": [
    {"description": "CHF 379 monitor at Digitec, bought there before", "expected": "approve", "why": "one line, known seller, under CHF 400"},
    {"description": "CHF 379 monitor plus a CHF 29 cable", "expected": "decline", "why": "a second line you did not ask for"}
  ],
  "open_questions": [
    {"question": "Which exact model did you choose?", "options": ["Dell U2723QE", "LG 27UP850", "Another model, I will say which"],
     "confirming_answers": ["Dell U2723QE", "LG 27UP850"], "answer": null}
  ],
  "uncertainty_policy": "ask"
}

The customer sees plain_english, the examples and the open questions in the Wallet and confirms or rejects there. The backend evaluates rules only; examples are your own claims and are shown, not enforced."""


class PolicyMCPServer(MCPServer):
    """Policy authoring MCP with per-agent authenticated tools."""

    def __init__(self, identities: IdentityStore, stdio_agent_token: str | None = None):
        super().__init__("Leash Policy Authoring", instructions=SERVER_INSTRUCTIONS)
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
    *,
    app_origin: str,
) -> PolicyMCPServer:
    wallet_origin, _ = _validate_origin(app_origin)
    identity_store = identities or IdentityStore(store.root)
    server = PolicyMCPServer(identity_store, stdio_agent_token)

    @server.resource("policy://authoring-guide", mime_type="application/json")
    def policy_authoring_guide() -> dict[str, Any]:
        """Read the exact fields and restrictions for a customer policy proposal."""
        server.require_agent("policy:read")
        return authoring_guide()

    @server.tool()
    def begin_pairing(agent_label: str) -> dict[str, Any]:
        """Step 1 of the Leash flow: start pairing this agent with the customer's Wallet.

        agent_label is the name the customer sees on the approval screen, for example "Grocery helper".
        Returns pairing_code, verifier, expires_at (5 minutes), scopes and wallet_url. Give the customer
        only wallet_url. Keep verifier private for complete_pairing; never print it or place it in a URL.
        Call this once per session; a restart needs a new pairing.
        """
        try:
            pairing = identity_store.begin_pairing(agent_label)
        except ValueError as exc:
            raise ToolError(f"InvalidPairing: {exc}") from exc
        return {
            **pairing,
            "wallet_url": f"{wallet_origin}/app/?pair={quote(pairing['pairing_code'], safe='')}",
        }

    @server.tool()
    def complete_pairing(pairing_code: str, verifier: str) -> dict[str, Any]:
        """Step 2 of the Leash flow: finish pairing after the customer approved you in the Wallet.

        Pass the pairing_code and verifier from begin_pairing. Returns agent_id, account_id, scopes and
        agent_token. Over stdio the token is also kept inside this server and authenticates every later
        tool; over HTTP send it as a Bearer header. Never print or log the token. PairingPending means the
        customer has not approved yet: wait and retry. PairingUnknown means the code expired or was used:
        call begin_pairing again.
        """
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
        """Step 3 of the Leash flow: fetch the proposal format for one customer instruction.

        Pass the customer's sentence verbatim. Returns guide (allowed fields, operators, rule shape,
        example shape, question shape) and request_instructions. Read the guide before drafting; every
        rule field and operator must come from it. Requires pairing.
        """
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
        """Step 4 of the Leash flow: store a policy proposal for the customer to confirm in the Wallet.

        instruction is the customer's sentence verbatim. proposal has exactly rules, examples,
        open_questions and uncertainty_policy (ask, decline or approve), as in the server instructions'
        worked example. Each rule quotes an exact substring of the instruction as source_text and carries
        a plain_english sentence the customer reads. Returns the stored draft with draft_id, version and
        hash. Nothing is authorized by this call: tell the customer the draft is waiting in their Wallet
        (the Wallet lists it, and it opens at <wallet origin>/app/?draft_id=<draft_id>), then poll
        get_policy_status. InvalidDraft names the field that failed validation; fix it and resubmit.
        This tool does not buy anything.
        """
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
        """Step 5 of the Leash flow: poll a draft until the customer decides in the Wallet.

        Returns state pending, confirmed with mandate_id, or rejected with the customer's reason.
        Poll every few seconds; do not proceed to shopping on pending. On rejected, read the reason,
        draft a revised proposal and call propose_task_policy again. Read-only: confirmation happens
        only in the customer's Wallet, never through this server.
        """
        agent = server.require_agent("policy:read")
        _known(draft_id, agent["account_id"])
        return policy_status(store, draft_id)

    @server.tool()
    def get_policy_summary(draft_id: str) -> dict[str, Any]:
        """Read back what the customer sees for one of your drafts: plain-English rules, examples, open
        questions with any answers, and the uncertainty setting. Use it to explain the policy to the
        customer or to check a confirmed mandate before shopping. Read-only.
        """
        agent = server.require_agent("policy:read")
        _known(draft_id, agent["account_id"])
        return policy_summary(store, draft_id)

    @server.tool()
    def buy(
        mandate_id: str, cart: list[CartLine], merchant: CartMerchant, facts: list[PurchaseFacts]
    ) -> dict[str, Any]:
        """Step 6 of the Leash flow, parked in this demo: ask the Wallet to judge a purchase under a
        confirmed mandate_id. In the demo every purchase attempt arrives from the organizer's simulator
        and this call raises PurchasesParked. Do not retry it; report to the customer that purchases
        are judged by the Wallet from the simulator feed.
        """
        server.require_agent("policy:propose")
        raise PurchasesParked(PARKED_MESSAGE)

    @server.tool()
    def get_purchase_status(authorization_id: str) -> dict[str, Any]:
        """Read the decision (approve, decline or step_up) and step-up resolution of one purchase by
        authorization_id. Parked with buy in this demo: raises PurchasesParked. A step_up is answered
        only by the customer in the Wallet, never by you.
        """
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
    app_origin, _ = _validate_origin(os.environ.get("LEASH_APP_ORIGIN"))
    store = DraftStore(Path(root))

    identities = IdentityStore(store.root)
    if args.transport == "stdio":
        if args.port is not None:
            raise RuntimeError("--port only applies to --transport streamable-http")
        token = os.environ.get("LEASH_AGENT_TOKEN")
        create_server(store, identities, stdio_agent_token=token, app_origin=app_origin).run(transport="stdio")
        return

    if args.port is None:
        raise RuntimeError("--transport streamable-http requires --port")
    create_server(store, identities, app_origin=app_origin).run(
        transport="streamable-http", host=args.host, port=args.port
    )


if __name__ == "__main__":
    main()
