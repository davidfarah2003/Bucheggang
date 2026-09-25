"""Owned session storage before provider execution or MCP pairing is available."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, ValidationError

from leash.contracts._base import Contract

from .records import _file_lock, sync_directory

UUIDValue = Annotated[UUID, Field(strict=False)]
AccountId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class SessionNotFound(KeyError):
    """The requested session is absent or belongs to another account."""


class SessionConflict(RuntimeError):
    """An existing create key is bound to different input."""


class SessionStoreError(RuntimeError):
    """A saved session or create mapping cannot be trusted."""


class CreateSession(Contract):
    client_request_id: UUIDValue
    provider: Literal["anthropic"]
    model: Literal["claude-sonnet-5"]


class SessionMessage(Contract):
    client_message_id: UUIDValue
    expected_version: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1, max_length=8000)]


class PendingConnection(Contract):
    status: Literal["pending"]
    agent_id: None
    agent_label: Literal["Shopping Harness / Claude Sonnet 5"]
    scopes: tuple[Literal["policy:propose"], Literal["policy:read"]]
    pairing_expires_at: None


class UnboundStatus(Contract):
    policy: None
    purchase: None
    observed_at: None


class UnavailableActions(Contract):
    send_message: Literal[False]
    open_wallet: Literal[False]
    search: Literal[False]
    buy: Literal[False]


class AgentSession(Contract):
    """The initial snapshot. Later phases need their actual pairing/adapter implementation."""

    session_id: UUIDValue
    version: Annotated[int, Field(ge=1, le=1)]
    provider: Literal["anthropic"]
    model: Literal["claude-sonnet-5"]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    phase: Literal["pairing_required"]
    operation: None
    messages: Annotated[list, Field(max_length=0)]
    tool_calls: Annotated[list, Field(max_length=0)]
    errors: Annotated[list, Field(max_length=0)]
    connection: PendingConnection
    draft_id: None
    mandate_id: None
    authorization_id: None
    backend_status: UnboundStatus
    wallet_link: None
    available_actions: UnavailableActions


class StoredSession(Contract):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    account_id: AccountId
    request: CreateSession
    session: AgentSession


class CreateKey(Contract):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    account_id: AccountId
    client_request_id: UUIDValue
    input_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    session_id: UUIDValue


def _canonical(value: dict | list) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _account(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("session storage requires an authenticated account ID")
    return value


def _input_hash(request: CreateSession) -> str:
    return hashlib.sha256(_canonical(request.model_dump(mode="json", exclude={"client_request_id"}))).hexdigest()


def _publish(path: Path, value: dict) -> None:
    """Publish one complete 0600 JSON file exclusively; never replace an existing record."""
    temporary = path.parent / f".{uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class AgentSessionStore:
    def __init__(self, policy_root: Path):
        self.root = Path(policy_root).resolve(strict=True) / "agent-sessions"
        if not self.root.parent.is_dir():
            raise ValueError("session policy root is not a directory")

    def _prepare_directories(self, account_id: str) -> None:
        for folder in (self.root, self.root / "records", self.root / "records" / account_id,
                       self.root / "create-keys", self.root / ".locks"):
            folder.mkdir(mode=0o700, exist_ok=True)
            sync_directory(folder.parent)

    def _read(self, session_id: UUID, account_id: str) -> StoredSession:
        path = self.root / "records" / account_id / f"{session_id}.json"
        try:
            data = path.read_text()
        except FileNotFoundError as exc:
            raise SessionNotFound() from exc
        try:
            record = StoredSession.model_validate_json(data)
        except ValidationError:
            raise SessionStoreError("stored session schema is invalid") from None
        if (record.account_id != account_id or record.session.session_id != session_id
                or record.session.provider != record.request.provider
                or record.session.model != record.request.model):
            raise SessionStoreError("stored session identity or provider binding differs")
        return record

    def get_owned(self, session_id: UUID, account_id: str) -> AgentSession:
        account_id = _account(account_id)
        if not isinstance(session_id, UUID):
            raise ValueError("session_id must be a UUID")
        return self._read(session_id, account_id).session

    def create(self, account_id: str, request: CreateSession) -> tuple[AgentSession, bool]:
        """Create unpaired storage. The HTTP layer must establish adapter availability first."""
        account_id = _account(account_id)
        request = CreateSession.model_validate(request.model_dump(mode="python"))
        key = hashlib.sha256(_canonical([account_id, str(request.client_request_id)])).hexdigest()
        self._prepare_directories(account_id)
        stop_at = time.monotonic() + 5
        with _file_lock(self.root / ".locks" / f"create-{key}.lock", stop_at=stop_at):
            key_path = self.root / "create-keys" / f"{key}.json"
            if key_path.exists():
                try:
                    binding = CreateKey.model_validate_json(key_path.read_text())
                except ValidationError:
                    raise SessionStoreError("stored create-key schema is invalid") from None
                if binding.account_id != account_id or binding.client_request_id != request.client_request_id:
                    raise SessionStoreError("stored create key has a different owner or request ID")
                if binding.input_hash != _input_hash(request):
                    raise SessionConflict("create key was already used with different input")
                try:
                    record = self._read(binding.session_id, account_id)
                except SessionNotFound:
                    raise SessionStoreError("create key references a missing session; no second session was created") from None
                if record.account_id != account_id or record.request != request:
                    raise SessionStoreError("create key differs from its saved session")
                return record.session, False
            session_id = uuid4()
            now = datetime.now(UTC)
            session = AgentSession(
                session_id=session_id, version=1, provider=request.provider, model=request.model,
                created_at=now, updated_at=now, phase="pairing_required", operation=None,
                messages=[], tool_calls=[], errors=[], draft_id=None, mandate_id=None,
                authorization_id=None, wallet_link=None,
                connection=PendingConnection(
                    status="pending", agent_id=None, agent_label="Shopping Harness / Claude Sonnet 5",
                    scopes=("policy:propose", "policy:read"), pairing_expires_at=None,
                ),
                backend_status=UnboundStatus(policy=None, purchase=None, observed_at=None),
                available_actions=UnavailableActions(send_message=False, open_wallet=False, search=False, buy=False),
            )
            record = StoredSession(schema_version=1, account_id=account_id, request=request, session=session)
            binding = CreateKey(schema_version=1, account_id=account_id, client_request_id=request.client_request_id,
                                input_hash=_input_hash(request), session_id=session_id)
            _publish(key_path, binding.model_dump(mode="json"))
            with _file_lock(self.root / ".locks" / f"session-{session_id}.lock", stop_at=stop_at):
                _publish(self.root / "records" / account_id / f"{session_id}.json", record.model_dump(mode="json"))
            return session, True
