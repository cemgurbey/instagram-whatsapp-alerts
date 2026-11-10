"""WhatsApp Cloud API sender.

Alerts go out as *template* messages: WhatsApp only allows free-form
text inside a 24-hour customer-service window, and a DM alert is exactly
the kind of out-of-window notification templates exist for. The template
(see SETUP.md) is:

    ig_dm_alert:  "📩 Instagram DM\nFrom: {{1}}\n{{2}}"

where {{1}} is the sender label and {{2}} the rendered message.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("whatsapp")
GRAPH_BASE = "https://graph.facebook.com/v21.0"
MAX_BODY_CHARS = 1024  # WhatsApp template body parameter limit


class WhatsAppSender:
    def __init__(
        self,
        token: str,
        phone_number_id: str,
        recipient: str,
        template_name: str = "ig_dm_alert",
        template_lang: str = "en",
        dry_run: bool = False,
    ):
        self._token = token
        self._phone_number_id = phone_number_id
        self._recipient = recipient
        self._template_name = template_name
        self._template_lang = template_lang
        self._dry_run = dry_run

    async def send_alert(self, sender_label: str, body: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": self._recipient,
            "type": "template",
            "template": {
                "name": self._template_name,
                "language": {"code": self._template_lang},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": sender_label},
                            {"type": "text", "text": body[:MAX_BODY_CHARS]},
                        ],
                    }
                ],
            },
        }
        if self._dry_run:
            log.info("DRY_RUN WhatsApp send: %s", payload)
            return
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{GRAPH_BASE}/{self._phone_number_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        if resp.status_code >= 300:
            log.error("WhatsApp send failed: %s %s", resp.status_code, resp.text)
            resp.raise_for_status()

    async def send_batch(self, items: list[tuple[str, str]]) -> None:
        """Send the overnight queue as one combined alert."""
        lines = [f"{sender}: {text}" for sender, text in items]
        await self.send_alert("Instagram (while you were away)", "\n".join(lines))
