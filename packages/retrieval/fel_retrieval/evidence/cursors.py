"""Opaque pagination cursors (#395, MCP-402; design contract §6.3).

A cursor is a signed token carrying a keyset position, an expiry and a digest
of what it was issued for: the evidence context and the tool's frozen filters.
Used with a different context or filters it is ``invalid_input``; past its
lifetime it is ``cursor_expired``. The position is re-applied under the
visibility predicate on every page, so a cursor never widens what is visible.

The signing key and the clock are injected. Nothing here reads configuration,
the environment or the system clock, and the issue time never enters the
evidence context: token bytes may differ between replays, pages may not.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.limits import invalid_input

MAX_LIFETIME: Final = timedelta(minutes=15)
MIN_KEY_BYTES: Final = 32


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii") + b"=" * (-len(text) % 4))


def _binding(context: i.EvidenceContext, scope: Mapping[str, Any]) -> str:
    """Digest of the context and the tool's filters a cursor belongs to."""
    bound = dataclasses.asdict(context)
    bound["effective_as_of"] = context.effective_as_of.astimezone(UTC).isoformat()
    canonical = json.dumps({"context": bound, "scope": scope}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class CursorCodec:
    """Issues and reads cursors with an injected signing key and clock."""

    def __init__(
        self, key: bytes, clock: Callable[[], datetime], *, lifetime: timedelta = MAX_LIFETIME
    ) -> None:
        if len(key) < MIN_KEY_BYTES:
            raise ValueError(f"cursor signing key must be at least {MIN_KEY_BYTES} bytes")
        if not timedelta(0) < lifetime <= MAX_LIFETIME:
            raise ValueError("cursor lifetime must be positive and at most 15 minutes")
        self._key = key
        self._clock = clock
        self._lifetime = lifetime

    def _now(self) -> datetime:
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("the cursor clock must return timezone-aware instants")
        return now

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())

    def encode(
        self, context: i.EvidenceContext, scope: Mapping[str, Any], position: Sequence[Any]
    ) -> str:
        payload = {
            "b": _binding(context, scope),
            "e": (self._now() + self._lifetime).astimezone(UTC).isoformat(),
            "p": list(position),
        }
        body = _b64(json.dumps(payload, sort_keys=True).encode())
        return f"{body}.{self._mac(body)}"

    def decode(self, token: str, context: i.EvidenceContext, scope: Mapping[str, Any]) -> list[Any]:
        """The position, if the token is ours, for this context, and unexpired."""
        body, _, mac = token.partition(".")
        try:
            if not body.isascii() or not hmac.compare_digest(self._mac(body), mac):
                raise ValueError("signature")
            payload = json.loads(_unb64(body))
            bound, expires = payload["b"], datetime.fromisoformat(payload["e"])
            position = list(payload["p"])
        except (ValueError, KeyError, TypeError, binascii.Error):
            raise invalid_input("cursor", "is not a cursor issued by this server") from None
        if not hmac.compare_digest(bound, _binding(context, scope)):
            raise invalid_input("cursor", "was issued for a different context or filters")
        if self._now() >= expires:
            raise i.EvidenceReadError(
                "cursor_expired",
                "The cursor has expired.",
                retryable=False,
                recovery="Restart from the first page with the same pins and cutoff.",
            )
        return position
