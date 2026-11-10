"""FastAPI service: Instagram webhook in, WhatsApp template alert out.

Run with:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

from .config import Settings
from .filters import describe_message, in_quiet_hours
from .instagram import UsernameResolver, parse_events, verify_signature
from .store import Store
from .whatsapp import WhatsAppSender

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

settings = Settings.from_env()
store = Store(settings.database_path)
store.seed_exclusions(settings.excluded_senders)
sender = WhatsAppSender(
    token=settings.whatsapp_token,
    phone_number_id=settings.whatsapp_phone_number_id,
    recipient=settings.alert_recipient,
    template_name=settings.whatsapp_template_name,
    template_lang=settings.whatsapp_template_lang,
    dry_run=settings.dry_run,
)
resolver = UsernameResolver(settings.ig_user_access_token)


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def _quiet() -> bool:
    return in_quiet_hours(_now_local(), settings.quiet_start, settings.quiet_end)


async def _flush_loop() -> None:
    """Every minute: if quiet hours just ended, send the queued batch."""
    was_quiet = _quiet()
    while True:
        await asyncio.sleep(60)
        quiet = _quiet()
        if was_quiet and not quiet and store.queue_size():
            items = store.drain_queue()
            log.info("Flushing %d queued alerts", len(items))
            try:
                await sender.send_batch(items)
            except Exception:  # noqa: BLE001 — keep the loop alive
                log.exception("Batch flush failed")
        was_quiet = quiet


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_flush_loop())
    yield
    task.cancel()


app = FastAPI(title="Instagram -> WhatsApp DM Alerts", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "queued": store.queue_size()}


@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta's one-time webhook subscription handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("forbidden", status_code=403)


@app.post("/webhook")
async def webhook_receive(request: Request):
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_signature(settings.ig_app_secret, raw, signature):
        return PlainTextResponse("bad signature", status_code=403)

    payload = await request.json()
    for event in parse_events(payload):
        if not store.mark_processed(event.mid):
            continue  # duplicate delivery (Meta retries webhooks)
        name = await resolver.resolve(event.sender_id)
        # Muted conversation — the manual exclusion mirror. Matches on the
        # sender id or the username, whichever form was added to the list.
        if (
            store.is_excluded(event.sender_id)
            or store.is_excluded(name)
            or store.is_excluded(name.lstrip("@"))
        ):
            continue
        text = describe_message(event.text, event.attachments)
        if _quiet():
            store.enqueue(name, text)
        else:
            try:
                await sender.send_alert(name, text)
            except Exception:  # noqa: BLE001 — one failure must not 500 the webhook
                log.exception("Alert send failed for %s", event.mid)
    # Always 200 once the signature checks out, so Meta doesn't retry-storm.
    return {"status": "received"}
