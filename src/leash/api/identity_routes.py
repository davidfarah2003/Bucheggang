"""Wallet routes for reviewing MCP agent pairings and revoking agents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from leash.policy.identity import IdentityStore, PairingUnknown


def identity_router(
    identities: IdentityStore,
    current_customer_session: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/pairing/{code}")
    def get_pairing(
        code: str,
        session: dict[str, Any] = Depends(current_customer_session),
    ) -> dict:
        try:
            return identities.pairing_for_wallet(code)
        except PairingUnknown as exc:
            raise HTTPException(status_code=404, detail="pairing was not found") from exc

    @router.post("/pairing/{code}/approve", status_code=204)
    def approve_pairing(
        code: str,
        session: dict[str, Any] = Depends(current_customer_session),
    ) -> Response:
        try:
            identities.approve_pairing(code, session["account_id"])
        except PairingUnknown as exc:
            raise HTTPException(status_code=404, detail="pairing was not found") from exc
        return Response(status_code=204)

    @router.get("/agents")
    def list_agents(session: dict[str, Any] = Depends(current_customer_session)) -> list[dict]:
        return identities.agents_for_account(session["account_id"])

    @router.post("/agents/{agent_id}/revoke")
    def revoke_agent(
        agent_id: str,
        session: dict[str, Any] = Depends(current_customer_session),
    ) -> dict:
        try:
            return identities.revoke_agent(agent_id, session["account_id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent was not found for this account") from exc

    return router
