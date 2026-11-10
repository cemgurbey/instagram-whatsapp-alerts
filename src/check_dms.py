#!/usr/bin/env python3
"""Reference implementation of the Instagram -> WhatsApp alert core.

Polls the Instagram inbox through the connector CLI, diffs each thread
against the watermark stored in the state file, applies the exclusion
list (the manual mirror of Instagram's mute state, which the API does
not expose), and prints the WhatsApp alert that would be sent.

Delivery is intentionally out of scope: in the live system the alert
text is handed to the agent runtime, which posts it to WhatsApp. This
script covers everything deterministic — poll, diff, filter, format —
and advances the watermarks in the state file.

Usage:
    python3 check_dms.py --state state.json [--cli instagram-messages-cli]

Exit code is 0 whether or not there is anything new; when there is, the
alert text is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

QUIET_START = time(23, 0)
QUIET_END = time(8, 0)
MAX_QUOTE_CHARS = 200


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"account_id": "", "own_fbid": "", "excluded_threads": [], "threads": {}}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_cli(cli: str, *args: str) -> dict:
    out = subprocess.run(
        [cli, *args], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def in_quiet_hours(now: datetime) -> bool:
    t = now.time()
    return t >= QUIET_START or t < QUIET_END


def describe_message(msg: dict) -> str:
    """One-line rendering of a single incoming message."""
    content = msg.get("content") or {}
    text = (content.get("text_body") or "").strip()
    if text:
        return text if len(text) <= MAX_QUOTE_CHARS else text[: MAX_QUOTE_CHARS - 1] + "…"
    ctype = (msg.get("content_type") or "").lower()
    if "reel" in ctype or "clip" in ctype:
        return "sent a reel"
    if "photo" in ctype or "image" in ctype:
        return "sent a photo"
    if "video" in ctype:
        return "sent a video"
    if "story" in ctype:
        return "shared a story"
    if "audio" in ctype or "voice" in ctype:
        return "sent a voice message"
    return "sent a message"


def collect_new(state: dict, inbox: dict) -> tuple[list[tuple[str, list[str]]], dict]:
    """Return (alert blocks, updated thread watermarks).

    A block is (conversation title, rendered new messages). Threads on the
    exclusion list never produce a block, but their watermarks advance.
    """
    own = state["own_fbid"]
    excluded = set(state.get("excluded_threads", []))
    known = state.get("threads", {})
    blocks: list[tuple[str, list[str]]] = []
    watermarks: dict[str, dict] = dict(known)

    for thread in inbox.get("threads", []):
        tid = thread["thread_fbid"]
        messages = thread.get("messages", [])
        if not messages:
            continue
        newest = messages[-1]
        watermarks[tid] = {
            "title": thread.get("thread_title", tid),
            "last_msg_id": newest.get("message_id"),
            "last_ts": thread.get("last_activity_timestamp_ms"),
        }
        if tid in excluded:
            continue
        seen_ts = int(known.get(tid, {}).get("last_ts") or 0)
        new_incoming = [
            m
            for m in messages
            if int(m.get("timestamp") or 0) > seen_ts
            and m.get("sender_fbid") != own
        ]
        if new_incoming:
            rendered = [describe_message(m) for m in new_incoming]
            blocks.append((thread.get("thread_title", tid), rendered[:3]))

    return blocks, watermarks


def format_alert(blocks: list[tuple[str, list[str]]]) -> str:
    lines = ["📩 Instagram"]
    for title, rendered in blocks:
        if len(rendered) == 1:
            lines.append(f"• {title}: {rendered[0]}")
        else:
            lines.append(f"• {title}: " + " / ".join(rendered))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="state.json", help="state file path")
    parser.add_argument("--cli", default="instagram-messages-cli", help="connector CLI")
    parser.add_argument("--tz", default="America/Toronto", help="local timezone")
    args = parser.parse_args()

    state_path = Path(args.state)
    state = load_state(state_path)

    # Quiet hours: do nothing and advance nothing, so the morning run
    # batches everything that arrived overnight.
    if in_quiet_hours(datetime.now(ZoneInfo(args.tz))):
        return 0

    inbox = run_cli(
        args.cli,
        "inbox",
        "--account-id",
        state["account_id"],
        "--first",
        "30",
        "--message-count",
        "5",
    )

    blocks, watermarks = collect_new(state, inbox)
    state["threads"] = watermarks
    save_state(state_path, state)

    if blocks:
        print(format_alert(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
