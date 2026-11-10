# Instagram → WhatsApp DM Alerts

Get a WhatsApp message whenever someone sends you an Instagram DM — without
having to keep checking Instagram.

Every ~15 minutes a watcher polls the Instagram inbox, diffs it against a
per-conversation watermark, and forwards genuinely new messages to WhatsApp
with the message text (or a one-line summary). Late-night messages
(11 PM – 8 AM) are held and delivered as a morning batch.

Built as a scheduled agent task on top of an Instagram Messages connector;
this repo holds the watcher's instruction spec and a reference implementation
of its deterministic core (poll → diff → format) so the design is portable
and auditable.

**Deployable version included:** `app/` is a standalone FastAPI service that
does the same job with public APIs — Instagram Messaging API webhooks in
(no polling, alerts in seconds), WhatsApp Cloud API template messages out,
SQLite for dedupe/exclusions/the quiet-hours queue, Docker to run it
anywhere. Start with [SETUP.md](SETUP.md): the code is ready, but the Meta
app, the Instagram professional account, and the WhatsApp template approval
are steps only the account owner can do.

## How it works

1. **Poll** — read the 30 most recent inbox threads with a small message
   preview (`instagram-messages-cli inbox`).
2. **Diff** — compare each thread's newest activity against the stored
   watermark (`last_msg_id` / `last_ts`) in `state.json`. Anything older is
   ignored; messages sent by the account owner never alert.
3. **Filter** — threads on the exclusion list never alert (their watermarks
   still advance, so excluding a chat doesn't create a backlog later).
4. **Fetch** — if the preview doesn't cover all new messages in a thread,
   read the thread directly and take everything after the watermark.
5. **Format & deliver** — compose one WhatsApp message, one block per
   conversation:

   ```
   📩 Instagram
   • Jane: are we still on for Saturday?
   • Book Club: Alex sent a photo
   ```

   Text is quoted as-is when short; reels/photos/videos with no caption are
   reported as "sent a reel" / "sent a photo" / "sent a video".
6. **Save** — watermarks advance to the newest message seen, for every
   thread scanned.

## The mute problem

Instagram's API does **not** expose which conversations a user has muted.
So "only alert me for conversations I haven't muted" can't be read from
Instagram — it's mirrored in a manually maintained `excluded_threads` list
in the state file. Mute a conversation in the app, add it to the list, and
the watcher skips it. (Group chats that trade reels all day are the usual
first entries.)

## Quiet hours

Between 23:00 and 08:00 local time the watcher does nothing — and crucially
does **not** advance watermarks — so overnight messages surface in the first
morning run as a single batch instead of pinging at 3 AM.

## Files

- `watcher/INSTRUCTIONS.md` — the scheduled task's instruction spec: the
  exact procedure the agent follows on each run (poll, diff, filter, format,
  deliver, save), with placeholders for account/chat IDs.
- `src/check_dms.py` — reference implementation of the deterministic core:
  polls the inbox via the connector CLI, applies the watermark diff and the
  exclusion list, prints the alert that would be sent, and updates state.
  Delivery itself is one call in the agent runtime, so the script stops at
  composing the alert.
- `state.example.json` — the state file schema with placeholder data.
- `app/` — the deployable service (see above): `main.py` (webhook +
  quiet-hours flush loop), `instagram.py` (signature check, payload
  parsing, username lookup), `whatsapp.py` (Cloud API template sender),
  `store.py` (SQLite: dedupe, exclusions, queue), `filters.py` (quiet
  hours, message rendering), `exclusions.py` (CLI for the mute mirror).
- `SETUP.md` — end-to-end setup: Meta app, Instagram messaging access,
  WhatsApp number + template, hosting.
- `tests/` — unit tests for parsing, rendering, rules, and the store
  (`pip install -r requirements-dev.txt && pytest`).

## State file

```json
{
  "account_id": "<instagram account id>",
  "own_fbid": "<same id — used to ignore your own messages>",
  "excluded_threads": ["<thread id>", "..."],
  "threads": {
    "<thread id>": {
      "title": "Conversation name",
      "last_msg_id": "mid.…",
      "last_ts": "1793729412371"
    }
  }
}
```

The real state file is runtime data, not code — it's gitignored and never
committed.

## Limitations

- Polling, not push: alerts arrive within ~15 minutes, not instantly. That
  cadence is also a deliberate courtesy to the connector's rate guidance.
- Only the 30 most recently active threads are scanned per run.
- Mute state is a manual mirror (see above) — if you mute a conversation in
  Instagram and forget to list it, it will still alert once.
