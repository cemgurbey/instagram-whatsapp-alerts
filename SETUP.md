# Setup guide

The code is the easy half. This service needs two Meta integrations, and
both have steps only the account owner can do: creating the Meta app,
passing app review, and registering the WhatsApp number/template. Budget
an hour for the clicking, plus however long Meta takes on review.

## 0. Prerequisites

- An Instagram **Business or Creator** account (personal accounts can't
  use the messaging API). Convert in the Instagram app: Settings →
  Account type and tools → Switch to professional account.
- A Facebook account you can create developer apps with.
- A phone number for WhatsApp alerts (your own is fine) and a number to
  send from (Meta gives you a free test number; you can later register
  your own).

## 1. Create the Meta app

1. Go to [developers.facebook.com](https://developers.facebook.com) →
  My Apps → Create App → type **Other** → **Business**.
2. In the app dashboard, add two products: **Instagram** (the "Instagram
   API with Instagram Login" variant) and **WhatsApp**.
3. Note from Settings → Basic: the **App Secret** → `.env` as
   `IG_APP_SECRET`.

## 2. Instagram messaging access

1. In the Instagram product settings, connect your Instagram professional
   account and generate a user access token with the
   `instagram_business_manage_messages` permission → `.env` as
   `IG_USER_ACCESS_TOKEN` (exchange it for a 60-day long-lived token;
   production use requires renewing or a system-user token).
2. Webhooks (Instagram product → Webhooks): set the callback URL to
   `https://<your-host>/webhook`, the verify token to the value you put in
   `META_VERIFY_TOKEN`, and subscribe to the **messages** field.
   The service must already be running and publicly reachable over HTTPS
   for this step — Meta pings it during setup (see step 5 for hosting,
   or use a tunnel like cloudflared/ngrok for the first test).
3. **App review:** while the app is in Development mode, webhooks only
   fire for accounts with a role in the app (fine for alerting your own
   account — add yourself as admin/tester and you're done). Submitting
   for review is only needed to serve *other* people's accounts.

## 3. WhatsApp sender + alert template

1. WhatsApp product → API Setup: pick the sender phone number (start
   with the provided test number; add your own number as a recipient —
   the test setup only delivers to numbers you list).
2. Create a **permanent token**: Meta Business Settings → Users → System
   Users → add one with `whatsapp_business_messaging` permission, and
   generate its token → `.env` as `WHATSAPP_TOKEN`. Also copy the
   **Phone number ID** → `WHATSAPP_PHONE_NUMBER_ID`.
3. Create the alert template (WhatsApp → Message Templates → Create,
   category **Utility**):

   - Name: `ig_dm_alert` (must match `WHATSAPP_TEMPLATE_NAME`)
   - Language: English (must match `WHATSAPP_TEMPLATE_LANG`)
   - Body:

     ```
     📩 Instagram DM
     From: {{1}}
     {{2}}
     ```

   Template approval is usually fast for utility templates, but it is a
   real review — alerts can't send until it's **Approved**.

## 4. Configure and run

```bash
cp .env.example .env   # fill in every value; ALERT_RECIPIENT is your own
                       # WhatsApp number, digits only, country code first
docker compose up -d --build
curl http://localhost:8000/health
```

No Docker? `pip install -r requirements.txt` then
`uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Seed your muted list before going live (the mirror of Instagram's mute
state — the API doesn't expose it, so this stays manual):

```bash
EXCLUDED_SENDERS="noisy_group,brand_account" docker compose up -d
# afterwards:
docker compose exec web python -m app.exclusions add some_sender
docker compose exec web python -m app.exclusions list
```

## 5. Hosting (needs public HTTPS)

Webhooks require a public HTTPS URL. Any of these works:

- **Fly.io:** `fly launch` (the Dockerfile is picked up), `fly secrets set`
  for the `.env` values, `fly volumes create data --size 1` and mount it
  at `/data` so the SQLite state survives deploys.
- **Render / Railway:** point at the repo, set env vars, add a persistent
  disk at `/data`.
- **A VPS:** `docker compose up -d` behind Caddy or nginx with TLS.
- **Just testing:** `cloudflared tunnel --url http://localhost:8000`
  gives you a temporary public URL for the webhook handshake.

## 6. Verify end to end

1. From a *different* Instagram account, DM yourself something.
2. Within seconds a WhatsApp template message should arrive:
   "📩 Instagram DM / From: @sender / <your message>".
3. DM yourself again at night (or set `QUIET_START`/`QUIET_END` to cover
   now): nothing arrives; after quiet hours end, the batch lands as one
   message.

## Notes & limits

- Message *content* of shares (the actual reel/photo) isn't forwarded —
  the alert says "sent a reel", same judgement call as the agent version.
- Group DM threads arrive through the same webhook; exclude the noisy
  ones.
- Tokens expire if you use short-lived ones — if alerts silently stop,
  check the token first.
