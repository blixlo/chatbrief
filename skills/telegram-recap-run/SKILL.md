---
name: telegram-recap-run
description: What each scheduled ChatBrief run does - collect the read-only recap JSON, write the recap in plain sentences (or send the fallback), stay silent when there's nothing, stop with one short line on lock, flood, revoked session or bad settings. Also maps plain-chat settings requests to commands. ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
---

# ChatBrief run

Repo: `telegram-recap-agent/` (this box's copy: `/workspace/telegram-recap-agent`). From the repo root, using the Python printed by setup (`$PY`: the user's interpreter, or `.venv/bin/python` if install fell back to a venv):

`$PY -m tg_recap collect`

**Test or manual runs** (anything that isn't the scheduled routine, e.g. the owner says "show me a recap now" or you are checking that it works): use `$PY -m tg_recap collect --peek`. It does the same read-only pass but doesn't advance the window or write `state.json` at all (no window, no chat-title directory) and saves no recap copy, so the next scheduled run still covers the full period. Its JSON has `"peek": true`. The scheduled routine never uses `--peek`.

It prints one JSON object (read-only; nothing is sent, reacted to, or marked read). Keys:
`window` (start, end, tz), `length`, `needs_you` (chat, `kind`, who, one clean sentence; `kind` is `reply` for a reply to the owner's message, `mention` for an @mention of the owner, either a Telegram mention entity or `@handle` typed as plain text, or `keyword` for a non-bot message containing a priority keyword, with `keyword` set), `conversations` (per chat: name, new_messages, people, highlights, trimmed `messages`), `more_conversations`, `alert_feeds` (name, count, noun from the message pattern: trending alert, new listing, whale alert, buy/sell alert, alert or automated post; top tickers; `source` when one bot fed a group), `memecoin_mentions` (per token: `ticker`, `mentions`, `chats`, `chat_names`, `first_seen`, `biggest_buy` when a reported buy crossed the threshold, `address_sightings`/`distinct_addresses`; and when contract addresses are on (the default), `ca` is the most-seen public token CA, `ca_sightings` its count, `other_cas` how many other CAs were seen, `all_cas` every token-context CA seen for the coin as `{ca, sightings}` objects, most-seen first, and `links` up to 5 public token-page links (pump.fun, dexscreener, birdeye, solscan token pages, gmgn token pages) with queries and referral codes stripped; `all_cas` and `links` are for machine handoffs the owner approved, not for the recap text, and both are absent when contract addresses are off), `also_active` (muted chats with a count), `count_only`, `quiet_count`, `show_disclaimer`, `disclaimer`, `fallback_text`, `nothing_to_report`.

## Exit codes

- **Exit 0, `nothing_to_report: true`:** send nothing.
- **Exit 0 otherwise:** write the recap (rules below) and send it to the owner.
- **Exit 2 `LOCK_HELD`:** send one line: "ChatBrief skipped this run because another run was using the session. It will try again at the next scheduled time." Then stop.
- **Exit 3 `SESSION_REVOKED`:** send one line: "Your Telegram session isn't active anymore (maybe ended in Settings > Devices). Say 'set up ChatBrief' to sign in again." Then stop.
- **Exit 4 `FLOOD_STOP`:** send one line: "Telegram asked ChatBrief to slow down, so this run stopped. It will try again at the next scheduled time." Then stop.
- **Exit 5 `NOT_SET_UP`:** send one line asking the owner to run setup. Then stop.
- **Exit 6 `MISSING_DEPS`:** send one line: "Telethon or websockets isn't installed for the Python this run used. Say 'set up ChatBrief' to install it again." Then stop.
- **Exit 8 `CONNECT_FAILED`:** couldn't reach Telegram's web endpoint (stderr names only the error type). Send one line: "ChatBrief couldn't reach Telegram this run (<error type>). It will try again at the next scheduled time." Then stop. Don't retry, and don't change anything.
- **Exit 9 `CONSENT_REQUIRED`:** the owner hasn't accepted the Telegram API terms (1.5) warning. Installs set up before v0.1.8 hit this on their first run after the upgrade. Nothing was read. Send the warning exactly as `$PY -m tg_recap consent show` prints it, and ask the owner to confirm in chat with an explicit yes. Run `$PY -m tg_recap consent accept` only after that explicit yes (never on silence, a question, or your own judgement), then the next scheduled run works. Until then, stop after sending the warning; don't retry.
- **Exit 7 `SETTINGS_INVALID`:** send one line: "Your recap settings have a problem (<the field from stderr>). Say 'show my recap settings' to fix it." Then stop.
- **Anything else:** send one short line that the run failed and setup can be rerun. Don't paste tracebacks.

## Writing the recap

Write from the JSON only, in plain sentences. Layout, in this order (skip empty sections):

1. Header: `ChatBrief · <window>`, with both dates and a short zone label, exactly like the first line of `fallback_text` (for example `Nov 10, 3:20 AM to Nov 11, 3:20 AM PT`).
2. **Needs you** first: each `needs_you` item by its `kind`: "<who> replied to you in <chat>: ...", "<who> mentioned you in <chat>: ...", or "<who> in <chat> (keyword '<keyword>'): ...". Say what's waiting on the owner.
   **Memecoin mentions** right after Needs you (or right after the header if Needs you is empty): one line per `memecoin_mentions` item, in the given order, at most 10, then "…and N more" if there are more. Each line matches `fallback_text`: ticker, then when `ca` is present " · CA `<addr>` (seen N×)" with the address in a markdown code span, plus "+M other CAs seen" if `other_cas` is above 0; if there is no ticker, lead with that CA phrase. Then mentions and chats, first seen time, the biggest reported buy if present, then the chat names. If `ca` is missing (the owner turned addresses off with `settings set memecoin-show-ca off`), use "same address seen N×" when `address_sightings` is 2 or more ("addresses seen N×" if `distinct_addresses` is above 1) and do not print any address. Never call a coin a buy, early, or good. Public CAs belong only in this section of the owner's recap; never include a CA in any Parlor post, or in any message that is not the recap.
3. **Conversations**, one short paragraph or 1-3 bullets per chat (fewer for `short`, more for `detailed`): what happened, what was decided, and any dates. Summarize; don't list messages. Mention `more_conversations` in one line if it's above 0.
4. **Alert feeds**, below the human conversations: one line each, e.g. "Whale Watch: 90 whale alerts, mostly ABC and XYZ." With `source`, tie it to the chat: "Lab Group: 1 trending alert from Some Bot (TI)." Say "mostly A and B" only when count is above 1 and there are two tickers; otherwise put the one ticker in brackets. Messages marked `summarized` are bot cards already reduced to a summary; never expand or quote them.
5. **Also active** (muted chats) and **Count only**, one line each with counts. Then "<quiet_count> other chats had no new messages." Never call a chat with new messages quiet.
6. If `show_disclaimer` is true, end with exactly one line: `Recap only, not financial advice.` Otherwise leave it out.

Rules:
- Lead with what needs the owner. Keep it short; match `length`.
- No raw message dumps and no long quotes. Quote a few words only when the exact wording matters.
- Don't repeat secrets, codes, passwords, personal wallet addresses, phone numbers, invite links or IDs. The JSON already removes most of them; don't reconstruct them. Public token CAs from `memecoin_mentions[].ca` should be printed in a code span in the Memecoin mentions section (that is how the owner tells coins apart). Don't invent or restore a CA that isn't in that field, and never print a CA in any other section. Never include a CA in any Parlor post.
- Name people only by the sender display names that appear in the JSON. Don't add other names of private people, usernames, or IDs.
- No trading or financial opinions, predictions, or advice.
- If you can't write it (the JSON is unclear, or something fails), send `fallback_text` exactly as it is.

## Settings from plain chat

Map the owner's words to one command, run it, and reply with the one line it prints. Never ask for Telegram codes or passwords here.

| The owner says | Run |
|---|---|
| "show my recap settings" | `$PY -m tg_recap settings show` |
| "make it shorter" / "longer" / "more detail" | `settings set length short` / `standard` / `detailed` |
| "mute Whale Watch in my recap" / "skip <chat>" | `settings chat "Whale Watch" skip` |
| "only count <chat>" | `settings chat "<chat>" count-only` |
| "always include <chat>" | `settings chat "<chat>" include` |
| "back to normal for <chat>" | `settings chat "<chat>" default` |
| "hide / show muted chats" | `settings set include-muted off` / `on` |
| "include archived chats" | `settings set include-archived on` |
| "leave out my DMs" | `settings set include-dms off` |
| "show alert bots in full" / "collapse alert bots" | `settings set collapse-alert-bots off` / `on` |
| "flag anything about invoices" | `settings keyword add invoice` (remove: `settings keyword remove invoice`) |
| "hide / show token contract addresses" | `settings set memecoin-show-ca off` / `on` (default on) |
| "only cover these chats" / "stop covering every other chat" / "cover all my chats again" | first mark each wanted chat with `settings chat "<chat>" include`, then `settings set only-included-chats on` (off: `settings set only-included-chats off`; default off). When on, every chat without an include or count-only rule, including chats joined later, is left out and not read. |
| "use Berlin time" | `settings set timezone Europe/Berlin` |
| "send it every 4 hours" / "daily at 9" | see Change frequency in `telegram-recap-setup` |

If a chat command prints "matches more than one chat", ask the owner which one, listing the titles it printed, and run it again with the exact title. Don't guess. If it prints "no chat called ...", say the chat will be known after the next recap run. Never show internal chat keys or IDs.

**Never patch your own code, transport, or connection/proxy settings at runtime** (no editing `tg_recap/`, no env vars or flags to change how it connects, no other client library). On exit 8 `CONNECT_FAILED`, tell the user in one line and stop. Exit 3 also covers a session whose data center or auth key Telegram no longer accepts; never work around it.

Never retry within a run, never start `login` yourself, never ask for codes or passwords, and never call any other Telegram action. Don't save the recap anywhere else; the code keeps its own fallback copy for at most 72 hours. `$PY -m tg_recap run` prints only the fallback text and still works for older routines.
