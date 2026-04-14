from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass, field
from secrets import compare_digest

from fastapi import Depends, Request

from ..api.dependencies import get_settings
from ..core.config import Settings
from ..core.errors import AuthenticationError, AuthorizationError


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_canonical_message(
    *,
    method: str,
    path: str,
    query: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            path,
            query,
            timestamp,
            nonce,
            body_hash,
        ]
    )


def sign_message(secret: str, canonical_message: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        canonical_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class HmacAuthContext:
    key_id: str
    scopes: frozenset[str]
    timestamp: int


@dataclass
class NonceStore:
    ttl_seconds: int
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _items: dict[str, float] = field(default_factory=dict)

    def remember(self, scope: str, nonce: str) -> None:
        now = time.time()
        key = f"{scope}:{nonce}"
        with self._lock:
            self._purge(now)
            if key in self._items:
                raise AuthenticationError("Replay request detected.")
            self._items[key] = now + float(self.ttl_seconds)

    def _purge(self, now: float) -> None:
        expired = [key for key, expires_at in self._items.items() if expires_at <= now]
        for key in expired:
            self._items.pop(key, None)


_nonce_stores: dict[int, NonceStore] = {}
_nonce_stores_lock = threading.Lock()


def _get_nonce_store(settings: Settings) -> NonceStore:
    ttl = settings.hmac_nonce_ttl_seconds
    with _nonce_stores_lock:
        store = _nonce_stores.get(ttl)
        if store is None:
            store = NonceStore(ttl_seconds=ttl)
            _nonce_stores[ttl] = store
        return store


async def verify_hmac_request(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HmacAuthContext:
    key_id = (request.headers.get("X-Key-Id") or "").strip()
    timestamp_text = (request.headers.get("X-Timestamp") or "").strip()
    nonce = (request.headers.get("X-Nonce") or "").strip()
    signature = (request.headers.get("X-Signature") or "").strip().lower()

    if not key_id or not timestamp_text or not nonce or not signature:
        raise AuthenticationError("Missing HMAC authentication headers.")

    secret = settings.hmac_keys.get(key_id)
    if not secret:
        raise AuthenticationError("Unknown HMAC key id.")

    try:
        timestamp_value = int(timestamp_text)
    except ValueError as exc:
        raise AuthenticationError("Invalid X-Timestamp header.") from exc

    now = int(time.time())
    if abs(now - timestamp_value) > settings.hmac_allowed_clock_skew_seconds:
        raise AuthenticationError("Request timestamp is outside the allowed window.")

    body = await request.body()
    body_hash = sha256_hex(body)
    canonical_message = build_canonical_message(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        timestamp=timestamp_text,
        nonce=nonce,
        body_hash=body_hash,
    )
    expected_signature = sign_message(secret, canonical_message)
    if not compare_digest(expected_signature, signature):
        raise AuthenticationError("Invalid HMAC signature.")

    nonce_store = _get_nonce_store(settings)
    nonce_store.remember(key_id, nonce)
    scopes = frozenset(settings.hmac_scopes.get(key_id, set()))
    auth_context = HmacAuthContext(key_id=key_id, scopes=scopes, timestamp=timestamp_value)
    request.state.hmac_auth = auth_context
    return auth_context


def require_hmac_scopes(*required_scopes: str):
    async def _require_scope(
        auth: HmacAuthContext = Depends(verify_hmac_request),
    ) -> HmacAuthContext:
        if "*" in auth.scopes:
            return auth
        for scope in required_scopes:
            if scope in auth.scopes:
                return auth
        raise AuthorizationError(
            "HMAC key is authenticated but not authorized for this endpoint.",
            details={
                "key_id": auth.key_id,
                "required_scopes": list(required_scopes),
            },
        )

    return _require_scope
