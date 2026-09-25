"""Authenticated customer routes for policy drafts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, StrictInt

from .confirmation import MandateClient, confirm_policy
from .ownership import ConfirmationSetChanged, customer_mandate_locks, owned_drafts
from .global_policy import GlobalPolicyConflict, GlobalPolicyStore, validate_rules
from .store import DraftConflict, DraftStore, InvalidDraft


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt
    hash: str
    answers: dict[str, str]


class GlobalPolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: StrictInt
    expected_hash: str
    rules: list[dict[str, Any]]


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt
    hash: str
    reason: str


def policy_router(
    store: DraftStore,
    mandates: MandateClient,
    authenticated_customer: Callable[..., str],
) -> APIRouter:
    """Mount these routes only behind the app's customer login dependency."""
    router = APIRouter()
    global_policies = GlobalPolicyStore(store)

    @router.get("/global-policy")
    def get_global_policy(customer: str = Depends(authenticated_customer)) -> dict:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        return global_policies.read(customer)

    @router.put("/global-policy")
    def put_global_policy(body: GlobalPolicyBody, customer: str = Depends(authenticated_customer)) -> dict:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if not body.expected_hash:
            raise HTTPException(status_code=422, detail="expected_hash is required")
        try:
            with customer_mandate_locks(store, customer):
                rules = validate_rules(body.rules)
                return global_policies.replace(customer, body.expected_version, body.expected_hash, rules)
        except GlobalPolicyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (InvalidDraft, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ConfirmationSetChanged as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/drafts")
    def list_drafts(
        state: str = Query(default="all"), customer: str = Depends(authenticated_customer)
    ) -> list[dict]:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if state not in {"pending", "proposed", "confirming", "confirmed", "rejected", "all"}:
            raise HTTPException(status_code=422, detail="state must be pending, proposed, confirming, confirmed, rejected or all")
        items = []
        for owned in owned_drafts(store, customer):
            draft = owned["draft"]
            item_state = owned["state"]
            state_matches = state == "all" or state == item_state or (state == "pending" and item_state in {"proposed", "confirming"})
            if not state_matches:
                continue
            items.append({
                "draft_id": draft["draft_id"],
                "version": draft["version"],
                "hash": draft["hash"],
                "state": item_state,
                "instruction": draft["instruction"],
                "plain_english": [rule["plain_english"] for rule in draft["rules"]],
                "uncertainty_policy": draft["uncertainty_policy"],
                "open_questions": sum(question["answer"] is None for question in draft["open_questions"]),
                "created_at": draft["created_at"],
                "mandate_id": owned["mandate_id"],
            })
        return sorted(items, key=lambda item: (item["created_at"], item["draft_id"]), reverse=True)

    @router.get("/drafts/{draft_id}")
    def get_draft(draft_id: str, customer: str = Depends(authenticated_customer)) -> dict:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        try:
            return store.get_owned(draft_id, customer)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="draft was not found") from exc
        except InvalidDraft as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/drafts/{draft_id}/confirm")
    def confirm(
        draft_id: str, body: ConfirmBody, customer: str = Depends(authenticated_customer)
    ) -> dict:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        try:
            with customer_mandate_locks(store, customer):
                store.assert_owner(draft_id, customer)
                global_snapshot = global_policies.read(customer)
                return confirm_policy(
                    store,
                    mandates,
                    draft_id,
                    version=body.version,
                    hash_value=body.hash,
                    answers=body.answers,
                    confirmed_by=customer,
                    global_policy=global_snapshot,
                )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="draft was not found") from exc
        except DraftConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidDraft as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ConfirmationSetChanged as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/drafts/{draft_id}/reject", status_code=204)
    def reject(
        draft_id: str, body: RejectBody, customer: str = Depends(authenticated_customer)
    ) -> Response:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        try:
            with customer_mandate_locks(store, customer):
                store.assert_owner(draft_id, customer)
                store.reject(
                    draft_id,
                    version=body.version,
                    hash_value=body.hash,
                    rejected_by=customer,
                    reason=body.reason,
                )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="draft was not found") from exc
        except DraftConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidDraft as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ConfirmationSetChanged as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(status_code=204)

    return router
