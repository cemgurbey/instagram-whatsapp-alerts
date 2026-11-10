"""Unit tests for the deterministic core: parsing, rendering, rules, store."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.filters import describe_message, in_quiet_hours
from app.instagram import parse_events, verify_signature
from app.store import Store

TZ = ZoneInfo("America/Toronto")

SAMPLE_PAYLOAD = {
    "object": "instagram",
    "entry": [
        {
            "id": "ig-account-1",
            "time": 1794200000,
            "messaging": [
                {
                    "sender": {"id": "sender-1"},
                    "recipient": {"id": "ig-account-1"},
                    "timestamp": 1794200000000,
                    "message": {"mid": "mid-1", "text": "are we still on for Saturday?"},
                },
                {
                    "sender": {"id": "ig-account-1"},
                    "recipient": {"id": "sender-1"},
                    "timestamp": 1794200001000,
                    "message": {"mid": "mid-echo", "text": "yep!", "is_echo": True},
                },
                {
                    "sender": {"id": "sender-2"},
                    "recipient": {"id": "ig-account-1"},
                    "timestamp": 1794200002000,
                    "message": {
                        "mid": "mid-2",
                        "attachments": [{"type": "ig_reel"}],
                    },
                },
            ],
        }
    ],
}


def test_parse_events_skips_echoes():
    events = parse_events(SAMPLE_PAYLOAD)
    assert [e.mid for e in events] == ["mid-1", "mid-2"]
    assert events[0].text == "are we still on for Saturday?"
    assert events[1].attachments == [{"type": "ig_reel"}]


def test_parse_events_ignores_non_instagram():
    assert parse_events({"object": "page", "entry": []}) == []


def test_describe_message():
    assert describe_message("hello", []) == "hello"
    assert describe_message(None, [{"type": "ig_reel"}]) == "sent a reel"
    assert describe_message(None, [{"type": "image"}]) == "sent a photo"
    assert describe_message(None, [{"type": "video"}]) == "sent a video"
    assert describe_message(None, []) == "sent a message"
    long_text = "x" * 500
    assert len(describe_message(long_text, [])) == 200


def test_quiet_hours_wraps_midnight():
    assert in_quiet_hours(datetime(2026, 11, 9, 23, 30, tzinfo=TZ), "23:00", "08:00")
    assert in_quiet_hours(datetime(2026, 11, 10, 3, 0, tzinfo=TZ), "23:00", "08:00")
    assert in_quiet_hours(datetime(2026, 11, 10, 7, 59, tzinfo=TZ), "23:00", "08:00")
    assert not in_quiet_hours(datetime(2026, 11, 10, 8, 0, tzinfo=TZ), "23:00", "08:00")
    assert not in_quiet_hours(datetime(2026, 11, 9, 12, 0, tzinfo=TZ), "23:00", "08:00")
    assert not in_quiet_hours(datetime(2026, 11, 9, 22, 59, tzinfo=TZ), "23:00", "08:00")


def test_store_dedupe_exclusions_queue(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    assert store.mark_processed("mid-1") is True
    assert store.mark_processed("mid-1") is False  # duplicate delivery

    store.seed_exclusions(("noisy_user",))
    assert store.is_excluded("noisy_user")
    store.add_exclusion("group_chat")
    assert store.list_exclusions() == ["group_chat", "noisy_user"]
    store.remove_exclusion("group_chat")
    assert not store.is_excluded("group_chat")

    store.enqueue("@jane", "hello")
    store.enqueue("@alex", "sent a photo")
    assert store.queue_size() == 2
    assert store.drain_queue() == [("@jane", "hello"), ("@alex", "sent a photo")]
    assert store.queue_size() == 0


def test_verify_signature():
    import hashlib
    import hmac

    body = b'{"object":"instagram"}'
    secret = "test-secret"
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(secret, body, good)
    assert not verify_signature(secret, body, "sha256=deadbeef")
    assert not verify_signature(secret, body, None)
    # No secret configured -> verification disabled (dev mode).
    assert verify_signature("", body, None)
