"""Configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    # Meta / Instagram webhook
    meta_verify_token: str = ""          # META_VERIFY_TOKEN — you choose this
    ig_app_secret: str = ""              # IG_APP_SECRET — enables signature checks
    ig_user_access_token: str = ""       # IG_USER_ACCESS_TOKEN — username lookups

    # WhatsApp Cloud API
    whatsapp_token: str = ""             # WHATSAPP_TOKEN (permanent, system user)
    whatsapp_phone_number_id: str = ""   # WHATSAPP_PHONE_NUMBER_ID (sender)
    whatsapp_template_name: str = "ig_dm_alert"
    whatsapp_template_lang: str = "en"
    alert_recipient: str = ""            # ALERT_RECIPIENT — your number, E.164 digits

    # Behaviour
    timezone: str = "America/Toronto"
    quiet_start: str = "23:00"           # QUIET_START — local, inclusive
    quiet_end: str = "08:00"             # QUIET_END — local, exclusive
    excluded_senders: tuple[str, ...] = field(default_factory=tuple)  # seed list

    # Runtime
    database_path: str = "data/app.db"
    dry_run: bool = False                # DRY_RUN=1 logs sends instead of sending

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            meta_verify_token=env("META_VERIFY_TOKEN", ""),
            ig_app_secret=env("IG_APP_SECRET", ""),
            ig_user_access_token=env("IG_USER_ACCESS_TOKEN", ""),
            whatsapp_token=env("WHATSAPP_TOKEN", ""),
            whatsapp_phone_number_id=env("WHATSAPP_PHONE_NUMBER_ID", ""),
            whatsapp_template_name=env("WHATSAPP_TEMPLATE_NAME", "ig_dm_alert"),
            whatsapp_template_lang=env("WHATSAPP_TEMPLATE_LANG", "en"),
            alert_recipient=env("ALERT_RECIPIENT", ""),
            timezone=env("TIMEZONE", "America/Toronto"),
            quiet_start=env("QUIET_START", "23:00"),
            quiet_end=env("QUIET_END", "08:00"),
            excluded_senders=_csv(env("EXCLUDED_SENDERS", "")),
            database_path=env("DATABASE_PATH", "data/app.db"),
            dry_run=env("DRY_RUN", "") in ("1", "true", "yes"),
        )
