"""File-backed accounts, Wallet sessions and paired MCP agent identities."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

SCOPES = ("policy:propose", "policy:read")
PASSWORD_N, PASSWORD_R, PASSWORD_P, PASSWORD_DKLEN = 1 << 14, 8, 1, 32
PAIRING_LIFETIME = timedelta(minutes=5)
SESSION_IDLE_LIFETIME = timedelta(hours=12)
SESSION_ABSOLUTE_LIFETIME = timedelta(hours=24)
RATE_WINDOW = timedelta(seconds=60)
RATE_LIMIT = 5
_DUMMY_SALT = b"leash-login-dummy"
_DUMMY_PASSWORD = b"not-a-real-account-password"
_DUMMY_HASH = hashlib.scrypt(_DUMMY_PASSWORD, salt=_DUMMY_SALT, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=PASSWORD_DKLEN)


class AccountExists(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class LoginThrottled(Exception):
    pass


class Unauthorized(Exception):
    pass


class PairingUnknown(Exception):
    pass


class PairingPending(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("invalid identity timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("invalid identity timestamp") from exc
    if parsed.tzinfo is None:
        raise RuntimeError("invalid identity timestamp")
    return parsed.astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _encode_secret(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_secret(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _password_record(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=PASSWORD_DKLEN)
    return "scrypt${}${}${}${}${}".format(PASSWORD_N, PASSWORD_R, PASSWORD_P, _encode_secret(salt), _encode_secret(value))


def _verify_password(password: str, encoded: Any) -> bool:
    if not isinstance(encoded, str):
        raise RuntimeError("invalid saved password record")
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        raise RuntimeError("invalid saved password record")
    try:
        n, r, p = (int(value) for value in parts[1:4])
        salt, expected = _decode_secret(parts[4]), _decode_secret(parts[5])
    except (ValueError, TypeError) as exc:
        raise RuntimeError("invalid saved password record") from exc
    if (n, r, p) != (PASSWORD_N, PASSWORD_R, PASSWORD_P) or len(salt) != 16 or len(expected) != PASSWORD_DKLEN:
        raise RuntimeError("invalid saved password record")
    supplied = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(supplied, expected)


def _recent_attempts(values: Any, now: datetime) -> list[str]:
    if not isinstance(values, list):
        raise RuntimeError("invalid saved login attempts")
    cutoff, kept = now - RATE_WINDOW, []
    for value in values:
        parsed = _parse_timestamp(value)
        if parsed > now + timedelta(seconds=1):
            raise RuntimeError("invalid saved login attempt time")
        if parsed > cutoff:
            kept.append(value)
    return kept


class IdentityStore:
    """Local-demo identity records stored beside the policy store."""

    def __init__(self, policy_root: Path | str):
        self.root = Path(policy_root) / "identity"
        self.locks = self.root / ".locks"
        self.accounts = self.root / "accounts"
        self.sessions = self.root / "sessions"
        self.pairings = self.root / "pairings"
        self.agents = self.root / "agents"
        for directory in (self.root, self.locks, self.accounts, self.sessions, self.pairings, self.agents):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def _locked(self, key: str) -> Iterator[None]:
        name = hashlib.sha256(key.encode("utf-8")).hexdigest() + ".lock"
        descriptor = os.open(self.locks / name, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid identity record {path.parent.name}/{path.name}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"invalid identity record {path.parent.name}/{path.name}")
        return value

    @staticmethod
    def _sync_dir(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_new(path: Path, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        IdentityStore._sync_dir(path.parent)

    @staticmethod
    def _write_replace(path: Path, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = path.parent / f".{uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            IdentityStore._sync_dir(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _account_path(self, username: str) -> Path:
        return self.accounts / (_digest(username) + ".json")

    def _session_path(self, cookie: str) -> Path:
        return self.sessions / (_digest(cookie) + ".json")

    def _pairing_path(self, code: str) -> Path:
        return self.pairings / (_digest(code) + ".json")

    def _agent_path(self, token: str) -> Path:
        return self.agents / (_digest(token) + ".json")

    @staticmethod
    def _valid_username(username: str) -> bool:
        return isinstance(username, str) and 1 <= len(username) <= 80 and not any(c.isspace() for c in username)

    @staticmethod
    def _valid_password(password: str) -> bool:
        return isinstance(password, str) and 8 <= len(password) <= 256

    def register(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        if not self._valid_username(username):
            raise ValueError("username must contain 1 to 80 non-whitespace characters")
        if not self._valid_password(password):
            raise ValueError("password must contain 8 to 256 characters")
        path = self._account_path(username)
        with self._locked(f"account:{path.stem}"):
            account = {
                "account_id": secrets.token_hex(16),
                "username": username,
                "password": _password_record(password),
                "created_at": _timestamp(),
                "failed_logins": [],
            }
            try:
                self._write_new(path, account)
            except FileExistsError as exc:
                raise AccountExists from exc
            cookie = _encode_secret(secrets.token_bytes(32))
            self._create_session(account["account_id"], cookie)
            return account, cookie

    def _create_session(self, account_id: str, cookie: str) -> None:
        path = self._session_path(cookie)
        record = {"account_id": account_id, "created_at": _timestamp(), "last_seen_at": _timestamp()}
        with self._locked(f"session:{path.stem}"):
            self._write_new(path, record)

    def _unknown_attempts(self, now: datetime) -> None:
        path = self.root / "unknown_login.json"
        with self._locked("unknown-login-window"):
            try:
                attempts = _recent_attempts(self._read(path).get("failed_logins"), now)
            except FileNotFoundError:
                attempts = []
            if len(attempts) >= RATE_LIMIT:
                self._write_replace(path, {"failed_logins": attempts})
                raise LoginThrottled
            attempts.append(_timestamp(now))
            self._write_replace(path, {"failed_logins": attempts})

    def login(self, username: str, password: str) -> tuple[dict[str, Any], str]:
        if not self._valid_username(username) or not self._valid_password(password):
            raise InvalidCredentials
        path = self._account_path(username)
        with self._locked(f"account:{path.stem}"):
            try:
                account = self._read(path)
            except FileNotFoundError:
                now = _now()
                supplied = hashlib.scrypt(password.encode("utf-8"), salt=_DUMMY_SALT, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=PASSWORD_DKLEN)
                hmac.compare_digest(supplied, _DUMMY_HASH)
                self._unknown_attempts(now)
                raise InvalidCredentials
            if not isinstance(account.get("account_id"), str) or not account["account_id"] or account.get("username") != username:
                raise RuntimeError("invalid saved account record")
            now = _now()
            failures = _recent_attempts(account.get("failed_logins"), now)
            if len(failures) >= RATE_LIMIT:
                account["failed_logins"] = failures
                self._write_replace(path, account)
                raise LoginThrottled
            if not _verify_password(password, account.get("password")):
                failures.append(_timestamp(now))
                account["failed_logins"] = failures
                self._write_replace(path, account)
                raise InvalidCredentials
            account["failed_logins"] = []
            self._write_replace(path, account)
            cookie = _encode_secret(secrets.token_bytes(32))
            self._create_session(account["account_id"], cookie)
            return account, cookie

    def session(self, cookie: str | None) -> dict[str, Any] | None:
        if not isinstance(cookie, str) or not cookie or len(cookie) > 96:
            return None
        path = self._session_path(cookie)
        with self._locked(f"session:{path.stem}"):
            try:
                record = self._read(path)
            except FileNotFoundError:
                return None
            created, last_seen, now = _parse_timestamp(record.get("created_at")), _parse_timestamp(record.get("last_seen_at")), _now()
            if now - last_seen >= SESSION_IDLE_LIFETIME or now - created >= SESSION_ABSOLUTE_LIFETIME:
                path.unlink()
                self._sync_dir(path.parent)
                return None
            if not isinstance(record.get("account_id"), str) or not record["account_id"]:
                raise RuntimeError("invalid saved session record")
            record["last_seen_at"] = _timestamp(now)
            self._write_replace(path, record)
            return record

    def logout(self, cookie: str) -> bool:
        if not isinstance(cookie, str) or not cookie:
            return False
        path = self._session_path(cookie)
        with self._locked(f"session:{path.stem}"):
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            self._sync_dir(path.parent)
            return True

    def account_for_id(self, account_id: str) -> dict[str, Any]:
        found = None
        for path in self.accounts.glob("*.json"):
            account = self._read(path)
            if account.get("account_id") == account_id:
                if found is not None:
                    raise RuntimeError("duplicate account ID in identity store")
                found = account
        if found is None:
            raise RuntimeError("session refers to an unknown account")
        return found

    def begin_pairing(self, agent_label: str) -> dict[str, Any]:
        if not isinstance(agent_label, str) or not 1 <= len(agent_label) <= 80:
            raise ValueError("agent_label must contain 1 to 80 characters")
        self._delete_expired_pairings()
        code = _encode_secret(secrets.token_bytes(16))
        verifier = _encode_secret(secrets.token_bytes(32))
        now = _now()
        record = {
            "verifier_digest": _digest(verifier),
            "agent_label": agent_label,
            "scopes": list(SCOPES),
            "status": "begun",
            "account_id": None,
            "created_at": _timestamp(now),
            "expires_at": _timestamp(now + PAIRING_LIFETIME),
        }
        path = self._pairing_path(code)
        with self._locked(f"pairing:{path.stem}"):
            self._write_new(path, record)
        return {"pairing_code": code, "verifier": verifier, "expires_at": record["expires_at"], "scopes": list(SCOPES)}

    def _delete_expired_pairings(self) -> None:
        now = _now()
        for path in self.pairings.glob("*.json"):
            with self._locked(f"pairing:{path.stem}"):
                try:
                    record = self._read(path)
                except FileNotFoundError:
                    continue
                if _parse_timestamp(record.get("expires_at")) <= now:
                    path.unlink()
                    self._sync_dir(path.parent)

    def pairing_for_wallet(self, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code:
            raise PairingUnknown
        path = self._pairing_path(code)
        with self._locked(f"pairing:{path.stem}"):
            try:
                record = self._read(path)
            except FileNotFoundError as exc:
                raise PairingUnknown from exc
            if record.get("status") != "begun" or _parse_timestamp(record.get("expires_at")) <= _now():
                raise PairingUnknown
            return {key: record[key] for key in ("agent_label", "scopes", "expires_at")}

    def approve_pairing(self, code: str, account_id: str) -> None:
        if not account_id:
            raise Unauthorized
        path = self._pairing_path(code)
        with self._locked(f"pairing:{path.stem}"):
            try:
                record = self._read(path)
            except FileNotFoundError as exc:
                raise PairingUnknown from exc
            if record.get("status") != "begun" or _parse_timestamp(record.get("expires_at")) <= _now():
                raise PairingUnknown
            record["status"] = "approved"
            record["account_id"] = account_id
            self._write_replace(path, record)

    def complete_pairing(self, code: str, verifier: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code or not isinstance(verifier, str) or not verifier:
            raise PairingUnknown
        path = self._pairing_path(code)
        with self._locked(f"pairing:{path.stem}"):
            try:
                record = self._read(path)
            except FileNotFoundError as exc:
                raise PairingUnknown from exc
            if record.get("status") in {"consumed", "failed"} or _parse_timestamp(record.get("expires_at")) <= _now():
                raise PairingUnknown
            if not hmac.compare_digest(_digest(verifier), str(record.get("verifier_digest", ""))):
                raise PairingUnknown
            if record.get("status") != "approved":
                raise PairingPending
            account_id = record.get("account_id")
            if not isinstance(account_id, str) or not account_id:
                raise RuntimeError("approved pairing has no account")
            record["status"] = "consumed"
            self._write_replace(path, record)
            token = _encode_secret(secrets.token_bytes(32))
            agent_id = str(uuid4())
            now = _timestamp()
            agent = {"agent_id": agent_id, "account_id": account_id, "agent_label": record["agent_label"], "scopes": list(record["scopes"]), "created_at": now, "last_used_at": now, "revoked_at": None}
            token_path = self._agent_path(token)
            with self._locked("agents-index"):
                self._write_new(token_path, agent)
            return {"agent_token": token, "agent_id": agent_id, "account_id": account_id, "scopes": agent["scopes"]}

    def agents_for_account(self, account_id: str) -> list[dict[str, Any]]:
        with self._locked("agents-index"):
            agents = [self._read(path) for path in self.agents.glob("*.json")]
        selected = [agent for agent in agents if agent.get("account_id") == account_id]
        return sorted(selected, key=lambda agent: (agent["created_at"], agent["agent_id"]), reverse=True)

    def revoke_agent(self, agent_id: str, account_id: str) -> dict[str, Any]:
        with self._locked("agents-index"):
            for path in self.agents.glob("*.json"):
                record = self._read(path)
                if record.get("agent_id") != agent_id:
                    continue
                if record.get("account_id") != account_id:
                    raise KeyError(agent_id)
                with self._locked(f"agent:{path.stem}"):
                    record = self._read(path)
                    if record.get("account_id") != account_id or record.get("agent_id") != agent_id:
                        raise KeyError(agent_id)
                    if record.get("revoked_at") is None:
                        record["revoked_at"] = _timestamp()
                        self._write_replace(path, record)
                    return record
        raise KeyError(agent_id)

    def authenticate_agent(self, token: str | None) -> dict[str, Any]:
        if not isinstance(token, str) or not token or len(token) > 96:
            raise Unauthorized
        path = self._agent_path(token)
        with self._locked(f"agent:{path.stem}"):
            try:
                record = self._read(path)
                if (
                    not isinstance(record.get("account_id"), str)
                    or not record["account_id"]
                    or not isinstance(record.get("agent_id"), str)
                    or not record["agent_id"]
                    or not isinstance(record.get("agent_label"), str)
                    or not record["agent_label"]
                    or record.get("scopes") != list(SCOPES)
                    or record.get("revoked_at") is not None
                ):
                    raise Unauthorized
                _parse_timestamp(record.get("created_at"))
                _parse_timestamp(record.get("last_used_at"))
            except FileNotFoundError as exc:
                raise Unauthorized from exc
            except RuntimeError as exc:
                raise Unauthorized from exc
            record["last_used_at"] = _timestamp()
            self._write_replace(path, record)
            return record
