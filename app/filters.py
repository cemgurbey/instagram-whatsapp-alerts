"""Quiet hours and message rendering — the judgement-free core rules."""

from __future__ import annotations

from datetime import datetime, time

MAX_QUOTE_CHARS = 200


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    """True when ``now`` (already localised) falls in the quiet window.

    The window may wrap midnight (the default 23:00 -> 08:00 does).
    """
    t = now.time()
    s, e = _parse_hhmm(start), _parse_hhmm(end)
    if s <= e:
        return s <= t < e
    return t >= s or t < e


def describe_message(text: str | None, attachments: list[dict]) -> str:
    """One-line rendering of an incoming message for the alert body."""
    if text and text.strip():
        text = text.strip()
        if len(text) <= MAX_QUOTE_CHARS:
            return text
        return text[: MAX_QUOTE_CHARS - 1] + "…"
    if attachments:
        kind = (attachments[0].get("type") or "").lower()
        if kind in ("ig_reel", "reel", "clip", "share"):
            return "sent a reel"
        if kind in ("image", "photo"):
            return "sent a photo"
        if kind == "video":
            return "sent a video"
        if kind == "audio":
            return "sent a voice message"
        if kind in ("story_mention", "story_reply"):
            return "mentioned you in a story"
    return "sent a message"
