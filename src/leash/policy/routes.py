"""Authenticated customer routes for policy drafts."""

from __future__ import annotations

from collections.abc import Callable
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictInt

from .confirmation import MandateClient, confirm_policy
from .store import DraftConflict, DraftStore, InvalidDraft


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt
    hash: str
    answers: dict[str, str]


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
    @router.get("/drafts/{draft_id}")
    def get_draft(draft_id: str, customer: str = Depends(authenticated_customer)) -> dict:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        try:
            return store.get(draft_id)
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
            return confirm_policy(
                store,
                mandates,
                draft_id,
                version=body.version,
                hash_value=body.hash,
                answers=body.answers,
                confirmed_by=customer,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="draft was not found") from exc
        except DraftConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidDraft as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/drafts/{draft_id}/reject", status_code=204)
    def reject(
        draft_id: str, body: RejectBody, customer: str = Depends(authenticated_customer)
    ) -> Response:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        try:
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
        return Response(status_code=204)

    return router
