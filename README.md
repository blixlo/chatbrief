# ChatBrief

**ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.**

**At a glance**

- Telegram API Terms section 1.5 restricts using Telegram data for AI; an AI-written recap may fall under it, so read the terms and accept the risk yourself (`consent accept`, see below).
- Read-only: it never sends, posts, reacts or marks anything read in Telegram.
- Main focus: memecoin mentions across your chats (tokens seen in several chats, big reported buys, with the public contract address when one is known), plus a general chat recap.
- Install: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python -m tg_recap --help`.
- Recap only, not financial advice.

Source code: https://github.com/blixlo/chatbrief. No license is granted; all rights reserved.

A personal recap of your own Telegram that you run yourself. It reads the groups, chats and channels you are already in and sends you one short summary of what is worth your attention, mentions of you first. Read-only. Any topic. Recaps are not financial advice.

## Privacy first: how the session works

ChatBrief signs in **as you**, using Telethon (a standard Telegram client library) on your own machine. It reads your chats through your existing account session, the same way your Telegram app does. No bot is added to your groups, and nobody in them sees anything new. It only reads: it doesn't post, react, join, or leave.

**How it connects:** only to Telegram's official web endpoints (`wss://pluto|venus|aurora|vesta|flora.web.telegram.org/apiws`, the same ones Telegram Web uses) over normal HTTPS on port 443, as a standard WebSocket carrying Telegram's own encrypted MTProto. Data centers are picked by number from that fixed list, never from an IP address. There is no proxy option and none is used.

Your phone number, login code, and two-step password are used once to sign in and are never saved or logged. We never see them, and neither does anyone else's machine. Only three things are kept on your machine, readable only by you (folder `~/.tg_recap`, mode 0700, files 0600): your API ID, your API hash, and Telegram's session file. The session file is a full key to your account: treat it like a password. You can end that session any time in Telegram under **Settings > Devices**.

It never marks messages as read, so your chats stay unread in your own apps.

## Setup (self-serve)

1. Get your own API ID and API hash at [my.telegram.org](https://my.telegram.org) (official steps: [core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id)).
2. Install, using your own Python (a virtual environment is optional, not required):
   ```
   ./install.sh
   ```
   That runs `"${PYTHON:-python3}" -m pip install --user -r requirements.txt`. If pip refuses because this Python is externally managed (PEP 668), it creates a local `.venv` and installs there instead. Note the Python it prints (your `python3`, or `.venv/bin/python` on fallback) and use that for every later command. You can also set `PYTHON` first (`PYTHON=python3 ./install.sh`), or install yourself:
   ```
   python3 -m pip install --user -r requirements.txt
   ```
   If that is refused, the venv fallback is:
   ```
   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
   ```
   `python3 -m pip install --user .` (or `pip install .` inside a venv) also works: `pyproject.toml` pins Telethon 1.45.0 and websockets 17.4.

   The commands below use `python3`; substitute `.venv/bin/python` if install fell back to a venv.
3. Read the terms warning (see "Telegram API terms" below) and, if you agree, run `python3 -m tg_recap consent accept`. Then sign in once. The default is resumable steps, each reading one value from an env var (a Grok Bot secret-request card sets these): `login --cards save-api` (`TG_RECAP_API_ID`, `TG_RECAP_API_HASH`), `send-code` (`TG_RECAP_PHONE`), `sign-in` (`TG_RECAP_CODE`, plus `TG_RECAP_PHONE` again; the phone is never stored on disk), and `password` (`TG_RECAP_2FA`, only after exit 10). `login --cards reset` clears an unfinished sign-in. Exit codes: 0 ok, 1 failed, 2 lock held, 4 flood stop, 5 not set up, 10 need 2FA, 11 wrong code, 12 wrong password, 13 code expired (start again at send-code), 14 bad phone, 15 bad API values, 16 env var missing (named), 17 no sign-in in progress. Between steps, `~/.tg_recap/pending/` (0700, files 0600) holds Telethon's pending session and the code hash; it's removed on success. Plain `login` only prints the steps.

   Fallbacks: `login --terminal` asks for the same values in a terminal (API hash and password hidden); `login --web` serves a page on `http://127.0.0.1:...`. Never paste a code or password into a chat. Nothing you enter is printed or logged. With a pip install, `tg-recap login ...` works too.
4. Pick how often: `python3 -m tg_recap set-frequency daily` (default), `every-4-hours`, `hourly`, or `custom --hours N` (minimum 1). Hourly runs about 24 times a day and uses more of your Grok Bot plan. Timezone defaults to America/Los_Angeles (`--timezone`).
5. Schedule `python3 -m tg_recap collect` (JSON for an agent to write the recap from) or `python3 -m tg_recap run` (the built-in fallback text) with the cron shown by `status`.

## Commands

| Command | What it does |
|---|---|
| `python -m tg_recap login --cards STEP` | Default sign-in: `save-api`, `send-code`, `sign-in`, `password`, `reset` |
| `python -m tg_recap login --terminal` / `--web` | Fallbacks: terminal prompts / page on 127.0.0.1 |
| `python -m tg_recap status` | Local status, cron and last recap time. Never contacts Telegram |
| `python -m tg_recap set-frequency ...` | Save frequency/timezone, print the cron |
| `python -m tg_recap collect` | One recap run. Prints JSON for the agent (plus `fallback_text`) |
| `python -m tg_recap consent show` / `consent accept` | Show the Telegram API terms (1.5) warning / record your yes (needed before sign-in, `collect` and `run`) |
| `python -m tg_recap run` | One recap run. Prints the fallback recap, or nothing |
| `... collect --peek` / `... run --peek` | Test or manual run: same full read, but the window isn't advanced and `state.json` isn't written at all (no window, no chat-title directory); no recap copy is saved. JSON has `"peek": true` |
| `python -m tg_recap settings show` | Your settings, no IDs |
| `python -m tg_recap settings set NAME VALUE` | `length`, `include-muted`, `include-archived`, `include-dms`, `collapse-alert-bots`, `timezone`, `priority-keywords`, `frequency`, `daily-hour` |
| `python -m tg_recap settings chat TITLE include\|skip\|count-only\|default` | Per-chat rule (fuzzy title match; ambiguity is reported) |
| `python -m tg_recap settings keyword add\|remove WORD` | Priority keywords, flagged first |
| `python -m tg_recap sample` | Prints a sample recap from fake example data |

`run`/`collect` exit codes: 0 ok, 9 the terms warning hasn't been accepted (`consent accept`), 2 another run holds the session lock, 3 session not active (sign in again), 4 Telegram asked to slow down twice, 5 not set up yet, 7 `settings.json` didn't validate, 8 couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket handshake or timeout; one line naming only the error type, after at most 2 attempts; sign-in steps use the same code). Any command exits 6 if Telethon 1.45.0 or websockets 17.4 isn't installed for that Python (stderr is one line telling you to `pip install -r requirements.txt`); stdout stays empty.

**Existing sessions (v0.1.5 and earlier)** keep working: the same `session.session` file and auth key are used; only the transport changed. On first use the stored data-center address is rewritten to that data center's web host. If the session points at a data center outside 1-5, or Telegram no longer knows the auth key, `run` exits 3 with a clear line and nothing is worked around: sign in again.

## What a recap contains

Header with both dates and a short zone label (`ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT`), then:

1. **Needs you:** replies to your own messages, @mentions of you (Telegram mention entities, or `@yourname` typed as plain text), and any message containing one of your priority keywords (not from bots). Posts made as your own channel never count as you. Each shows the sender and one clean sentence, cut at a word boundary with an ellipsis.
2. **Memecoin mentions:** tokens that show up in 2+ chats (or 5+ times in one chat from 2+ people), or that have two or more reported buys at or above the threshold (default 10 SOL or $2,000). Each line shows the ticker and, by default, the most-seen public contract address in a code span (so you can tell coins apart), plus mention counts and any big reported buy. Hide addresses with `settings set memecoin-show-ca off`.
3. **Conversations:** what happened, what was decided, dates. With `collect`, the agent writes these in plain sentences from trimmed messages; `run` prints a sentence-style fallback.
4. **Alert feeds:** automated feeds collapse to one line each, below the conversations (e.g. `Whale Watch: 90 whale alerts, mostly ABC and XYZ`). A feed is a DM with a bot, a chat whose new messages all came from bots (even one), a chat where bots sent at least 60% of 3+ new messages, or a chat where one sender sent at least 80% of 5+ messages that look templated. A bot posting in a group shows once, tied to that group (`Lab Group: 1 trending alert from Some Bot (TI)`); the same alerts in its DM aren't repeated. The noun comes from the messages (trending alert, new listing, whale alert, buy/sell alert, alert, automated post), not the bot's name. Tickers are `$TICKER` or plain ALL-CAPS words of 2-10 characters; anything that looks like an address or a fragment of one is skipped. Bot cards are summarised (`Trending alert (TI)`), never quoted: tree glyphs (├ └ │) and raw stat lines are stripped, and text is cut only at a sentence or word boundary. Turn off with `settings set collapse-alert-bots off`.
5. **Also active:** muted chats with a count (on by default). **Count only:** chats you set to count-only.
6. `N other chats had no new messages.` A chat with new messages is never counted as quiet.
7. `Recap only, not financial advice.` only when market or crypto chats appear.

Length (`short`, `standard`, `detailed`) sets the caps: characters per message (200/300/500), messages per chat (15/30/60), total characters (6k/15k/40k) and chats shown (6/10/20). In conversations and other recap text, wallet-like strings, t.me links, phone numbers and numeric IDs are removed. Public token contract addresses are shown only in the Memecoin mentions section (off with `settings set memecoin-show-ca off`). Personal wallet addresses stay hidden.

## Telegram API terms (section 1.5) and consent

[Telegram's API Terms of Service](https://core.telegram.org/api/terms), section 1.5, say: "you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."

This is an AI agent that reads your chats to write recaps, so before sign-in it shows this warning and asks you to confirm:

> ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
>
> Before you sign in: Telegram's API Terms of Service, section 1.5 (https://core.telegram.org/api/terms), say:
> "you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."
>
> ChatBrief is an AI agent that reads your chats to write your recaps. Telegram may consider that against its API terms. Telegram's stated remedy for a breach is to notify the account responsible for the app, and if it isn't fixed within 10 days, to cut off that app's access to the Telegram API (your API ID). ChatBrief never trains on your chats or uses them to build any model. Use it at your own risk.
>
> To continue, confirm that you have read this and accept the risk.

`python -m tg_recap consent show` prints it; `python -m tg_recap consent accept` records your yes as exactly two keys in `~/.tg_recap/settings.json` (0600): `tos_1_5_accepted_at` (ISO time) and `terms_version` (`tg-api-tos-1.5/2026-11-11`). Nothing else is stored. Until then every sign-in path (`login --cards` except `reset`, `--terminal`, `--web`), `collect` and `run` exit **9 `CONSENT_REQUIRED`** with one line, without contacting Telegram.

**Upgrading an existing install (v0.1.7 or earlier):** there is no consent record yet, so scheduled runs exit 9 after the upgrade until you accept. The run skill has the agent show the warning and ask you to confirm in chat; it runs `consent accept` only after your explicit yes. Your session and settings are untouched.

## Settings

`~/.tg_recap/settings.json` (0600, folder 0700), validated with defaults: `include_muted` true, `include_archived` false, `include_dms` true, `length` standard, `collapse_alert_bots` true, `priority_keywords` empty, `memecoin_show_ca` true, `memecoin_buy_sol` 10, `memecoin_buy_usd` 2000, `frequency`/`timezone` (stored for the schedule; the code uses the timezone), and per-chat rules stored by an internal salted chat key with the title. Chat titles for matching come from the last recap run (kept in `state.json`, titles only). Raw Telegram IDs are never stored or shown. An older `config.json` is read once if `settings.json` doesn't exist yet. See `docs/sample_recap_v0.1.5.md` for a synthetic example.

## Retention (this code's own cache)

Fetched data is deleted right after the recap is rendered. Rendered recap text is kept for at most 72 hours, then deleted on the next run. This covers only files this code writes; it does not touch Telegram or your apps.

## Open question

Telegram API Terms of Service section 1.5 (rules on AI and machine-learning use of Telegram data) and how it applies to an AI-written personal recap is an **open, unresolved question**. Read the [terms](https://core.telegram.org/api/terms) and decide for yourself before using this; the consent step above makes that an explicit choice.

## Self-serve

This is a template you run on your own machine with your own account. Nobody else logs in, inspects, or holds your session. No wallet keys or seeds are involved; it does hold Telegram account access through the session file.

## Development

Install test deps for the same interpreter install used (`requirements-dev.txt` also pulls in `requirements.txt`):

```
python3 -m pip install --user -r requirements-dev.txt && python3 -m pytest -q
```

(fully offline, fake client). If install fell back to a venv, use `.venv/bin/python -m pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q` instead. `./install.sh --dev` does that install step. You can also `pip install -e ".[dev]"`. Plain `pytest` from the repo root works too, without installing the package (`pythonpath = ["."]` in `pyproject.toml`).

## Product name

The name shown to users lives in one place: `PRODUCT_NAME` in `tg_recap/branding.py` (currently "ChatBrief"). Telegram's API terms: the title must not include "Telegram" (2.3), the disclosure above must stay in the description and docs (2.2), and no Telegram logo or icon may be used (2.4). Code, CLI help and the recap header read the constant; the generated code skills render it. To rename: edit the constant, run `python3 tools/apply_branding.py --from "<old name>"` (README, docs and skill copies), then `python3 tools/build_code_skill.py`. `tests/test_branding.py` fails if any user-facing text still uses another name.
