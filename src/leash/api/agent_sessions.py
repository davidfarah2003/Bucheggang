"""Owned session readback with provider operations unavailable until their adapter lands."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from leash.runner.agent_sessions import (
    AgentSession,
    AgentSessionStore,
    CreateSession,
    SessionMessage,
    SessionNotFound,
    SessionStoreError,
)
from leash.runner.settings import HarnessSettings


def _error(status: int, code: str, stage: str, message: str, session: AgentSession | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": {"code": code, "stage": stage, "message": message},
        "session_id": str(session.session_id) if session is not None else None,
        "version": session.version if session is not None else None,
    })


def agent_session_router(
    store: AgentSessionStore, authenticated_customer: Callable[..., str], configuration: HarnessSettings,
) -> APIRouter:
    router = APIRouter()

    def unavailable(session: AgentSession | None = None) -> JSONResponse:
        message = "The shopping provider is disabled."
        if configuration.enabled:
            message = "The shopping provider adapter is unavailable. No pairing or provider call was started."
        return _error(503, "provider_unconfigured", "configuration", message, session)

    def owned(session_id: UUID, account_id: str) -> AgentSession | JSONResponse:
        try:
            return store.get_owned(session_id, account_id)
        except SessionNotFound:
            return _error(404, "session_not_found", "configuration", "The agent session was not found.")
        except SessionStoreError:
            return _error(500, "session_storage_error", "recovery", "The stored agent session could not be read.")

    @router.post("/agent-sessions")
    def create_session(body: CreateSession, customer: str = Depends(authenticated_customer)) -> JSONResponse:
        return unavailable()

    @router.get("/agent-sessions/{session_id}", response_model=AgentSession)
    def get_session(session_id: UUID, customer: str = Depends(authenticated_customer)) -> AgentSession | JSONResponse:
        return owned(session_id, customer)

    @router.post("/agent-sessions/{session_id}/messages")
    def send_message(
        session_id: UUID, body: SessionMessage, customer: str = Depends(authenticated_customer),
    ) -> JSONResponse:
        session = owned(session_id, customer)
        if isinstance(session, JSONResponse):
            return session
        return unavailable(session)

    return router
