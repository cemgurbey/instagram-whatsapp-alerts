"""Instagram webhook side: signature check, payload parsing, name lookup.

The webhook payload for an Instagram messaging subscription looks like::

    {"object": "instagram",
     "entry": [{"id": "<ig id>", "time": 1700000000,
                "messaging": [{"sender": {"id": "<igsid>"},
                               "recipient": {"id": "<ig id>"},
                               "timestamp": 1700000000000,
                               "message": {"mid": "...", "text": "...",
                                           "attachments": [{"type": "image"}]}}]}]}

Events with ``message.is_echo`` are the account owner's own outgoing
messages and are dropped here. Reactions and reads carry no ``message``
text payload we alert on and are ignored.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

import httpx

GRAPH_BASE = "https://graph.instagram.com/v21.0"


@dataclass
class IncomingMessage:
    mid: str
    sender_id: str
    text: str | None = None
    attachments: list[dict] = field(default_factory=list)
    timestamp_ms: int = 0


def verify_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """Check the X-Hub-Signature-256 header against the raw request body."""
    if not app_secret:
        return True  # dev mode: secret not configured, nothing to check against
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_events(payload: dict) -> list[IncomingMessage]:
    """Extract alertable incoming messages from a webhook payload."""
    events: list[IncomingMessage] = []
    if payload.get("object") != "instagram":
        return events
    for entry in payload.get("entry", []):
        for item in entry.get("messaging", []):
            message = item.get("message") or {}
            if message.get("is_echo"):
                continue  # our own outgoing message
            mid = message.get("mid")
            sender_id = (item.get("sender") or {}).get("id")
            if not mid or not sender_id:
                continue
            events.append(
                IncomingMessage(
                    mid=mid,
                    sender_id=sender_id,
                    text=message.get("text"),
                    attachments=message.get("attachments") or [],
                    timestamp_ms=int(item.get("timestamp") or 0),
                )
            )
    return events


class UsernameResolver:
    """Best-effort IGSID -> username lookup via the Graph API, cached.

    The webhook only carries opaque sender ids. Resolving a display name
    needs the account's access token; without one (or on any failure) we
    fall back to a neutral label rather than failing the alert.
    """

    def __init__(self, access_token: str):
        self._token = access_token
        self._cache: dict[str, str] = {}

    async def resolve(self, sender_id: str) -> str:
        if sender_id in self._cache:
            return self._cache[sender_id]
        name = "Someone"
        if self._token:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(
                        f"{GRAPH_BASE}/{sender_id}",
                        params={"fields": "username", "access_token": self._token},
                    )
                if resp.status_code == 200:
                    username = resp.json().get("username")
                    if username:
                        name = f"@{username}"
            except httpx.HTTPError:
                pass
        self._cache[sender_id] = name
        return name
