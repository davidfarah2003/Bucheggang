"""Customer routes served from the runner's files.

step_up_router: GET /step-ups/pending and POST /step-ups/{authorization_id}/answer.
history_router: GET /mandates/{mandate_id}/decisions and GET /decisions/{authorization_id}.

leash.api includes both behind the app's customer login dependency, the same way
it includes leash.policy.routes.policy_router. They read data/ written by the
run loop process, so they work from the API process.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, ConfigDict

from leash.contracts import Decision, Event, MandateState, StepUp, StepUpAnswer
from leash.policy.ownership import owned_confirmations
from leash.policy.store import DraftStore

from . import api, records
from .stepups import StepUpBook, StepUpError


class DecisionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    state_after: MandateState


class DecisionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    event: Event
    state_before: MandateState
    state_after: MandateState


def step_up_router(book: StepUpBook, authenticated_customer: Callable[..., str], store: DraftStore) -> APIRouter:
    """GET /step-ups/pending and POST /step-ups/{authorization_id}/answer.

    Mount only behind the app's customer login dependency, as policy_router is.
    """
    router = APIRouter()

    @router.get("/step-ups/pending")
    def pending(customer: str = Depends(authenticated_customer)) -> list[StepUp]:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        pending = []
        for mandate_id in owned_confirmations(store, customer):
            for step_up in book.pending(mandate_id):
                if step_up.event.mandate.mandate_id != mandate_id:
                    raise StepUpError(f"step-up {step_up.authorization_id} is saved under the wrong mandate")
                pending.append(step_up)
        return sorted(pending, key=lambda step_up: step_up.expires_at)

    @router.post("/step-ups/{authorization_id}/answer")
    def answer(authorization_id: str, body: StepUpAnswer, customer: str = Depends(authenticated_customer)) -> Any:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if body.authorization_id != authorization_id:
            raise HTTPException(status_code=422, detail="authorization_id in the path and body differ")
        confirmations = owned_confirmations(store, customer)
        try:
            step_up = book.get(authorization_id)
            if step_up.event.mandate.mandate_id not in confirmations:
                raise HTTPException(status_code=404, detail=f"no pending step-up {authorization_id}")
            return book.answer(body)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no pending step-up {authorization_id}") from exc
        except StepUpError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except api.ApiError as exc:
            raise HTTPException(status_code=502, detail=f"simulator refused resolve: HTTP {exc.status} {exc.body}") from exc

    return router


def history_router(authenticated_customer: Callable[..., str], store: DraftStore) -> APIRouter:
    """GET /mandates/{mandate_id}/decisions and GET /decisions/{authorization_id}.

    Mount only behind the app's customer login dependency, as step_up_router is.
    """
    router = APIRouter()

    @router.get("/mandates/{mandate_id}/decisions")
    def mandate_decisions(mandate_id: str, customer: str = Depends(authenticated_customer)) -> list[DecisionEntry]:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if mandate_id not in owned_confirmations(store, customer):
            raise HTTPException(status_code=404, detail=f"no decisions recorded for mandate {mandate_id}")
        try:
            return [DecisionEntry(**entry) for entry in records.mandate_history(mandate_id)]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no decisions recorded for mandate {mandate_id}") from exc

    @router.get("/decisions/{authorization_id}")
    def decision(authorization_id: str, customer: str = Depends(authenticated_customer)) -> DecisionDetail:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        confirmations = owned_confirmations(store, customer)
        try:
            detail = DecisionDetail(**records.decision_detail(authorization_id))
            if detail.event.mandate.mandate_id not in confirmations:
                raise HTTPException(status_code=404, detail=f"no decision recorded for {authorization_id}")
            return detail
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no decision recorded for {authorization_id}") from exc

    return router
