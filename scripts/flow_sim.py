"""End-to-end user flow against a running Wallet: pair, propose, confirm, buy, answer a step-up.

Drives the policy MCP server over stdio exactly as an agent client does, and the Wallet's
customer routes with a session cookie exactly as the browser app does. Prints each step's
result. Any failure raises; nothing is substituted.

    uv run --group classifier python scripts/flow_sim.py --origin http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

INSTRUCTION = ("Do the weekly grocery shopping online at supermarkets I already use. Never spend more than "
               "CHF 100 per order or CHF 250 in any 7-day window; groceries and household basics only. If unsure, ask.")
PROPOSAL = {
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
         "source_text": "I already use", "plain_english": "Require a prior approved purchase at this shop on this card."},
    ],
    "examples": [
        {"description": "CHF 84 order at Coop, bought there before", "expected": "approve", "why": "under both limits, known shop, groceries"},
        {"description": "CHF 120 order at Migros", "expected": "decline", "why": "over the CHF 100 per-order limit"},
    ],
    "open_questions": [
        {"question": "Do household basics include cleaning products and toiletries?",
         "options": ["Yes, include them", "No, food only"], "confirming_answers": ["Yes, include them", "No, food only"], "answer": None},
    ],
    "uncertainty_policy": "ask",
}


def facts_for(item_id: str, product_type: str) -> dict:
    return {
        "item_id": item_id, "product_type": product_type, "size": None, "return_days": None, "is_addon": False,
        "is_gift_card": False, "is_subscription": False, "is_protection_plan": False, "matches_request": True,
        "contains_instructions": False, "excerpt": None,
        "sources": {k: "agent_form" for k in ("product_type", "is_addon", "is_gift_card", "is_subscription", "is_protection_plan", "matches_request")},
        "conflicts": [],
    }


KNOWN_SHOP = {"merchant_id": "ME0001", "merchant_name": "Alpine Basket", "merchant_category": "groceries",
              "merchant_mcc": "5411", "merchant_country": "CH", "merchant_city": "Zurich"}
NEW_SHOP = {"merchant_id": "ME9999", "merchant_name": "Fresh Corner Market", "merchant_category": "groceries",
            "merchant_mcc": "5411", "merchant_country": "CH", "merchant_city": "Basel"}
GROCERY_CART = [{"item_id": "IT0001", "item_name": "Fresh produce selection", "item_category": "groceries",
                 "item_details": "Seasonal fruit and vegetables; a typical weekly produce basket.",
                 "unit_price_chf": 28.0, "quantity": 1}]


def step(name: str, value) -> None:
    print(f"\n== {name}")
    print(json.dumps(value, indent=1, default=str)[:1600])


class Wallet:
    def __init__(self, origin: str):
        self.origin = origin
        self.client = httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=60)

    def call(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {response.status_code} {response.text}")
        return response.json() if response.content else None


async def run(origin: str) -> None:
    wallet = Wallet(origin)
    username = f"demo_{secrets.token_hex(3)}"
    account = wallet.call("POST", "/account", json={"username": username, "password": "demo-password-1"})
    step("customer registered in the Wallet", account)

    env = {**os.environ, "LEASH_POLICY_STORE": str(ROOT / "data" / "policy"), "LEASH_APP_ORIGIN": origin}
    server = StdioServerParameters(command=str(ROOT / "scripts" / "mcp-stdio.sh"), args=[], env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            step("MCP server", {"name": init.server_info.name, "instructions_chars": len(init.instructions or "")})
            tools = await session.list_tools()
            step("tools", [t.name for t in tools.tools])

            async def tool(name: str, **args):
                result = await session.call_tool(name, args)
                text = "".join(c.text for c in result.content if getattr(c, "text", None))
                if result.is_error:
                    raise RuntimeError(f"{name}: {text}")
                return json.loads(text) if text else None

            # 1. connect: the agent waits; the customer taps Approve in the Wallet.
            connect = asyncio.create_task(tool("connect", agent_label="Grocery helper", wait_seconds=60))
            pending = []
            for _ in range(30):
                pending = wallet.call("GET", "/pairings/pending")
                if pending:
                    break
                await asyncio.sleep(0.5)
            step("Wallet shows the pending connection", pending)
            wallet.call("POST", f"/pairings/{pending[0]['pairing_id']}/approve")
            paired = await connect
            step("agent connected", paired)

            # 2. propose the policy
            guide = await tool("get_policy_authoring_instructions", instruction=INSTRUCTION)
            step("authoring guide fields", sorted(guide["guide"].keys()))
            draft = await tool("propose_task_policy", instruction=INSTRUCTION, proposal=PROPOSAL)
            step("draft stored", {k: draft[k] for k in ("draft_id", "version", "hash")})

            # 3. the customer sees it in the Wallet and confirms
            listed = wallet.call("GET", "/drafts")
            mine = [d for d in listed if d["draft_id"] == draft["draft_id"]]
            step("Wallet lists the draft", mine[0] if mine else listed)
            waiter = asyncio.create_task(tool("wait_for_policy", draft_id=draft["draft_id"], wait_seconds=120))
            await asyncio.sleep(1)
            t0 = time.perf_counter()
            confirmed = wallet.call("POST", f"/drafts/{draft['draft_id']}/confirm", json={
                "version": draft["version"], "hash": draft["hash"],
                "answers": {PROPOSAL["open_questions"][0]["question"]: "Yes, include them"},
            })
            step(f"customer confirmed in {time.perf_counter() - t0:.1f}s", confirmed)
            status = await waiter
            step("agent saw the confirmation", status)
            mandate_id = status["mandate_id"]

            # 4. buy at a known shop: expected approve (history on CA0001 at ME0001)
            t0 = time.perf_counter()
            first = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12), cart=GROCERY_CART,
                               merchant=KNOWN_SHOP, delivery_fee_chf=7.0, total_chf=35.0,
                               facts=[facts_for("IT0001", "groceries")])
            step(f"buy #1 at a known shop judged in {time.perf_counter() - t0:.1f}s", first)

            # 5. buy at a shop the card never used: the merchant rule fails -> decline
            second = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12), cart=GROCERY_CART,
                                merchant=NEW_SHOP, delivery_fee_chf=7.0, total_chf=35.0,
                                facts=[facts_for("IT0001", "groceries")])
            step("buy #2 at an unknown shop", {k: second[k] for k in ("decision", "reason_codes", "customer_message")})

            # 6. a cart with an unknown fact under uncertainty_policy ask -> step_up, answered in the Wallet
            unsure = facts_for("IT0001", "groceries")
            unsure["is_addon"] = None
            del unsure["sources"]["is_addon"]
            unsure["matches_request"] = None
            del unsure["sources"]["matches_request"]
            third = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12),
                               cart=[{**GROCERY_CART[0], "unit_price_chf": 41.0}],
                               merchant=KNOWN_SHOP, delivery_fee_chf=7.0, total_chf=48.0, facts=[unsure])
            step("buy #3 with unknown facts", {k: third[k] for k in ("decision", "reason_codes", "customer_message")})
            if third["decision"] == "step_up":
                pending = wallet.call("GET", "/step-ups/pending")
                step("Wallet shows the pending purchase", [{"id": p["authorization_id"], "expires_at": p["expires_at"]} for p in pending])
                waiter = asyncio.create_task(tool("wait_for_purchase", authorization_id=third["authorization_id"], wait_seconds=60))
                await asyncio.sleep(1)
                answer = wallet.call("POST", f"/step-ups/{third['authorization_id']}/answer", json={
                    "authorization_id": third["authorization_id"], "decision": "approve",
                    "customer_message": "Yes, go ahead.", "answered_at": "2026-09-25T10:00:00Z",
                })
                step("customer answered in the Wallet", answer)
                final = await waiter
                step("agent received the answer", {k: final[k] for k in ("decision", "reason_codes", "customer_message")})

            # 7. a second order from the same agent at the known shop: the agent is now a known device
            fourth = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12),
                                cart=[{**GROCERY_CART[0], "item_id": "IT0002", "item_name": "Dairy and bread basket", "unit_price_chf": 22.5}],
                                merchant=KNOWN_SHOP, delivery_fee_chf=7.0, total_chf=29.5,
                                facts=[facts_for("IT0002", "groceries")])
            step("buy #4, same agent again", {k: fourth[k] for k in ("decision", "reason_codes", "customer_message")})

            history = wallet.call("GET", f"/mandates/{mandate_id}/decisions")
            step("Wallet history", [{"id": h["decision"]["authorization_id"], "decision": h["decision"]["decision"],
                                     "reasons": h["decision"]["reason_codes"]} for h in history])
            detail = wallet.call("GET", f"/decisions/{first['authorization_id']}")
            step("model checks on buy #1", [c for c in detail["decision"]["evidence"] if c["source"] == "model"])


async def run_manual(origin: str) -> None:
    """The agent's side of the demo; every wait returns when the customer acts in the Wallet."""
    env = {**os.environ, "LEASH_POLICY_STORE": str(ROOT / "data" / "policy"), "LEASH_APP_ORIGIN": origin}
    server = StdioServerParameters(command=str(ROOT / "scripts" / "mcp-stdio.sh"), args=[], env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def tool(name: str, **args):
                result = await session.call_tool(name, args)
                text = "".join(c.text for c in result.content if getattr(c, "text", None))
                if result.is_error:
                    raise RuntimeError(f"{name}: {text}")
                return json.loads(text) if text else None

            print("agent: a connection request is waiting in your Wallet", flush=True)
            paired = await tool("connect", agent_label="Grocery helper", wait_seconds=290)
            print("agent: connected", paired["agent_id"], flush=True)
            await tool("get_policy_authoring_instructions", instruction=INSTRUCTION)
            draft = await tool("propose_task_policy", instruction=INSTRUCTION, proposal=PROPOSAL)
            print("agent: policy proposed, waiting in your Wallet", draft["draft_id"], flush=True)
            status = await tool("wait_for_policy", draft_id=draft["draft_id"], wait_seconds=290)
            print("agent: policy", status["status"], status.get("mandate_id"), flush=True)
            mandate_id = status["mandate_id"]
            first = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12), cart=GROCERY_CART,
                               merchant=KNOWN_SHOP, delivery_fee_chf=7.0, total_chf=35.0,
                               facts=[facts_for("IT0001", "groceries")])
            print("agent: buy ->", first["decision"], first["reason_codes"], first["authorization_id"], flush=True)
            if first["decision"] == "step_up":
                final = await tool("wait_for_purchase", authorization_id=first["authorization_id"], wait_seconds=290)
                print("agent: customer answered ->", final["decision"], final["reason_codes"], flush=True)
            second = await tool("buy", mandate_id=mandate_id, purchase_key=secrets.token_hex(12), cart=GROCERY_CART,
                                merchant=NEW_SHOP, delivery_fee_chf=7.0, total_chf=35.0,
                                facts=[facts_for("IT0001", "groceries")])
            print("agent: buy at new shop ->", second["decision"], second["reason_codes"], flush=True)
            print("agent: done", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:8000")
    parser.add_argument("--manual", action="store_true",
                        help="agent side only: the customer approves, confirms and answers in the browser")
    args = parser.parse_args()
    asyncio.run(run_manual(args.origin) if args.manual else run(args.origin))


if __name__ == "__main__":
    sys.exit(main())
