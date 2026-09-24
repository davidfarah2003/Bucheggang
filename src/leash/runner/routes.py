"""Customer step-up routes: GET /step-ups/pending and POST /step-ups/{authorization_id}/answer.

leash.api includes this router behind the app's customer login dependency, the
same way it includes leash.policy.routes.policy_router.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from leash.contracts import StepUp, StepUpAnswer

from . import api
from .stepups import StepUpBook, StepUpError


def step_up_router(book: StepUpBook, authenticated_customer: Callable[..., str]) -> APIRouter:
    """GET /step-ups/pending and POST /step-ups/{authorization_id}/answer.

    Mount only behind the app's customer login dependency, as policy_router is.
    """
    router = APIRouter()

    @router.get("/step-ups/pending")
    def pending(customer: str = Depends(authenticated_customer)) -> list[StepUp]:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        return book.pending()

    @router.post("/step-ups/{authorization_id}/answer")
    def answer(authorization_id: str, body: StepUpAnswer, customer: str = Depends(authenticated_customer)) -> Any:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if body.authorization_id != authorization_id:
            raise HTTPException(status_code=422, detail="authorization_id in the path and body differ")
        try:
            return book.answer(body)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no pending step-up {authorization_id}") from exc
        except StepUpError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except api.ApiError as exc:
            raise HTTPException(status_code=502, detail=f"simulator refused resolve: HTTP {exc.status} {exc.body}") from exc

    return router
