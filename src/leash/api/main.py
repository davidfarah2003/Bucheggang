"""Customer app shell with local demo login and policy draft routes."""

from __future__ import annotations

import secrets
from threading import RLock

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from leash.policy.confirmation import MandateClient
from leash.policy.routes import policy_router
from leash.policy.store import DraftStore


COOKIE_NAME = "leash_session"


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str


def create_app(store: DraftStore, mandates: MandateClient) -> FastAPI:
    """Assemble customer routes with one local session store per app process."""
    from .static import mount_customer_app

    app = FastAPI(title="Agent on a Leash")
    sessions: dict[str, str] = {}
    sessions_lock = RLock()

    def authenticated_customer(leash_session: str | None = Cookie(default=None)) -> str:
        if leash_session is None:
            raise HTTPException(status_code=401, detail="customer login is required")
        with sessions_lock:
            customer = sessions.get(leash_session)
        if customer is None:
            raise HTTPException(status_code=401, detail="customer session is invalid or expired")
        return customer

    @app.post("/session")
    def login(body: LoginBody, response: Response) -> dict[str, str]:
        username = body.username.strip()
        if not username or len(username) > 80:
            raise HTTPException(status_code=422, detail="username must contain 1 to 80 characters")
        token = secrets.token_urlsafe(32)
        with sessions_lock:
            sessions[token] = username
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", path="/")
        return {"username": username}

    @app.get("/session")
    def current_session(customer: str = Depends(authenticated_customer)) -> dict[str, str]:
        return {"username": customer}

    @app.delete("/session", status_code=204)
    def logout(response: Response, leash_session: str = Cookie(),
               customer: str = Depends(authenticated_customer)) -> None:
        with sessions_lock:
            del sessions[leash_session]
        response.delete_cookie(COOKIE_NAME, path="/")

    app.include_router(policy_router(store, mandates, authenticated_customer))
    mount_customer_app(app)
    return app
