# Watcher instructions (scheduled task spec)

The task runs every 15 minutes as an agent job and delivers to the user's
WhatsApp chat. Placeholders: `<ACCOUNT_ID>` (Instagram account id),
`<WHATSAPP_CHAT_ID>` (the delivery chat), `<STATE_PATH>` (the state file).

---

Watch for new Instagram DMs and forward them to the user on WhatsApp.
Follow these steps exactly.

1. Read the state file `<STATE_PATH>`. It holds `account_id`, `own_fbid`
   (the user's own Instagram id), `excluded_threads` (thread_fbids of
   conversations the user has muted — never alert for these), and `threads`
   (per-thread watermark: last_msg_id and last_ts already seen).

2. Quiet hours: if the current local time (America/Toronto) is 23:00–08:00,
   end the run quietly with no report and change nothing — overnight
   messages are picked up by the morning runs because the watermarks stay
   untouched.

3. Run: `instagram-messages-cli inbox --account-id <ACCOUNT_ID> --first 30
   --message-count 5`. If this fails, end the run with a short failure note
   as the result and change nothing else.

4. For each returned thread:
   - Skip it entirely if its thread_fbid is in `excluded_threads` (but
     still update its watermark in state).
   - Compare its newest message with the stored watermark (last_ts /
     last_msg_id). No newer activity: nothing to do.
   - If the newest message is from the user himself (sender_fbid equals
     own_fbid), there is nothing new from the other side: just update the
     watermark.
   - Otherwise there are new incoming messages: collect every message in
     this thread newer than the watermark that was NOT sent by the user.
     If the preview does not show all of them, read the thread with
     `instagram-messages-cli thread --account-id <ACCOUNT_ID>
     --thread-fbid <id> --first 20` and take the messages after the
     watermark. Note the sender's name (for groups, the individual sender;
     otherwise the conversation title).

5. If there are new incoming messages in at least one thread, compose ONE
   WhatsApp alert, brief, one block per conversation:

   ```
   📩 Instagram
   • <Name>: <message>
   ```

   For a text message, quote it as-is if short (up to ~200 characters),
   otherwise a faithful one-line summary. For a reel/photo/video/story
   share with no text, write "sent a reel" / "sent a photo" / "sent a
   video" as fits. If several messages arrived in one conversation,
   summarize them in one line or list up to 3.
   Deliver the alert to `<WHATSAPP_CHAT_ID>` exactly as composed, with
   nothing added.

6. Update the state file: for every thread returned by the inbox call, set
   its watermark to the newest message id and last_activity_timestamp_ms
   observed this run; add previously unseen threads with their current
   watermark (alerting for them first if step 4 found new incoming
   messages). Write the file back even when nothing was new.

7. When nothing is new, end the run with no report at all — no message
   anywhere. The WhatsApp alert from step 5 is the only user-facing output
   of a successful run.
