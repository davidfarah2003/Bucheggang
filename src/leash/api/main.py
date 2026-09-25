"""Customer app shell with password login and file-backed sessions."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import IPv6Address, ip_address
import re
from urllib.parse import urlsplit
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictStr

from leash.policy.confirmation import MandateClient
from leash.policy.identity import AccountExists, IdentityStore, InvalidCredentials, LoginThrottled
from leash.policy.routes import policy_router
from leash.policy.store import DraftStore
from leash.runner.routes import step_up_router
from leash.runner.stepups import StepUpBook

from .identity_routes import identity_router

COOKIE_NAME = "leash_session"


class CredentialsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: StrictStr
    password: StrictStr


def _validate_origin(value: str) -> tuple[str, bool]:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(char == "\\" or ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise RuntimeError("LEASH_APP_ORIGIN must be an exact HTTP or HTTPS origin")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("LEASH_APP_ORIGIN has an invalid host or port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or hostname is None
        or (port is not None and not 1 <= port <= 65535)
        or f"{parsed.scheme}://{parsed.netloc}" != value
    ):
        raise RuntimeError("LEASH_APP_ORIGIN must be an exact HTTP or HTTPS origin without a path")
    if parsed.netloc.startswith("["):
        try:
            if "%" in hostname:
                raise ValueError("IPv6 zone identifiers are not supported")
            IPv6Address(hostname)
        except ValueError as exc:
            raise RuntimeError("LEASH_APP_ORIGIN has an invalid IP literal") from exc
    else:
        try:
            ip_address(hostname)
        except ValueError:
            labels = hostname.split(".")
            if len(hostname) > 253 or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            ):
                raise RuntimeError("LEASH_APP_ORIGIN has an invalid DNS hostname")
    return value, parsed.scheme == "https"


def create_app(
    store: DraftStore,
    mandates: MandateClient,
    step_up_book: StepUpBook,
    *,
    app_origin: str,
) -> FastAPI:
    """Mount the same-origin Wallet, account routes and protected lane APIs."""
    from leash.engine.state import load
    from leash.runner.routes import history_router
    from leash.runner.agent_sessions import AgentSessionStore
    from leash.runner.settings import load_harness

    from .agent_sessions import agent_session_router
    from .mandates import mandate_router
    from .static import mount_customer_app

    configured_origin, secure_cookie = _validate_origin(app_origin)
    harness_configuration = load_harness()
    agent_sessions = AgentSessionStore(store.root)
    identities = IdentityStore(store.root)
    app = FastAPI(title="Agent on a Leash")

    @app.middleware("http")
    async def check_mutation_origin(request: Request, call_next: Callable):
        unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        public_auth_post = request.method == "POST" and request.url.path in {"/account", "/session"}
        has_session_cookie = bool(request.cookies.get(COOKIE_NAME))
        if unsafe and (public_auth_post or has_session_cookie):
            origins = request.headers.getlist("origin")
            if origins != [configured_origin]:
                return JSONResponse(status_code=403, content={"detail": "request origin is not allowed"})
        response = await call_next(request)
        if request.url.path.rstrip("/") == "/app" and "pair" in request.query_params:
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def current_customer_session(
        leash_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    ) -> dict[str, Any]:
        record = identities.session(leash_session)
        if record is None:
            raise HTTPException(status_code=401, detail="customer session is invalid")
        account = identities.account_for_id(record["account_id"])
        return {
            "cookie": leash_session,
            "account_id": record["account_id"],
            "username": account["username"],
        }

    def authenticated_customer(session: dict[str, Any] = Depends(current_customer_session)) -> str:
        return session["account_id"]

    def set_session_cookie(response: Response, cookie: str) -> None:
        response.set_cookie(
            COOKIE_NAME,
            cookie,
            httponly=True,
            samesite="strict",
            secure=secure_cookie,
            path="/",
        )

    @app.post("/account", status_code=201)
    def register(body: CredentialsBody, response: Response) -> dict[str, str]:
        try:
            account, cookie = identities.register(body.username, body.password)
        except AccountExists as exc:
            raise HTTPException(status_code=409, detail="username is already registered") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        set_session_cookie(response, cookie)
        return {"account_id": account["account_id"], "username": account["username"]}

    @app.post("/session")
    def login(body: CredentialsBody, response: Response) -> dict[str, str]:
        try:
            account, cookie = identities.login(body.username, body.password)
        except LoginThrottled as exc:
            raise HTTPException(status_code=429, detail="too many login attempts; try again later") from exc
        except InvalidCredentials as exc:
            raise HTTPException(status_code=401, detail="username or password is wrong") from exc
        set_session_cookie(response, cookie)
        return {"account_id": account["account_id"], "username": account["username"]}

    @app.get("/session")
    def get_session(session: dict[str, Any] = Depends(current_customer_session)) -> dict[str, str]:
        return {"account_id": session["account_id"], "username": session["username"]}

    @app.delete("/session", status_code=204)
    def logout(
        response: Response,
        session: dict[str, Any] = Depends(current_customer_session),
    ) -> Response:
        if not identities.logout(session["cookie"]):
            raise HTTPException(status_code=401, detail="customer session is invalid")
        response.delete_cookie(COOKIE_NAME, path="/", secure=secure_cookie, httponly=True, samesite="strict")
        return Response(status_code=204, headers=response.headers)

    app.include_router(agent_session_router(agent_sessions, authenticated_customer, harness_configuration))
    app.include_router(identity_router(identities, current_customer_session))
    app.include_router(policy_router(store, mandates, authenticated_customer))
    app.include_router(mandate_router(store, authenticated_customer, load, step_up_book=step_up_book))
    app.include_router(step_up_router(step_up_book, authenticated_customer, store))
    app.include_router(history_router(authenticated_customer, store))
    mount_customer_app(app)
    return app
