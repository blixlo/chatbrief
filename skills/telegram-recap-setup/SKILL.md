---
name: telegram-recap-setup
description: First-run setup for ChatBrief - API disclosure and terms (1.5) consent, install, sign-in through secret-request cards (terminal or web page as fallbacks), frequency picker, and the bot's own routine. Also covers revoking and changing frequency. ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
---

# ChatBrief setup

Repo: `telegram-recap-agent/` (this box's copy: `/workspace/telegram-recap-agent`). Run every command from the repo root.

**Never** ask for the API ID, API hash, phone number, login code or two-step password in chat. The user enters each one only into its own secret-request card (or, on a fallback, into the terminal or page). You never see the values; never print, echo or read back the env vars. If the user pastes any of them in chat, don't use it; ask them to enter it in its card instead.

It connects only to Telegram's official web endpoints (`wss://<dc>.web.telegram.org/apiws`) over normal HTTPS (port 443). There is no proxy setting. **Never patch your own code, transport, or connection/proxy settings at runtime** (no editing `tg_recap/`, no env vars or flags to change how it connects, no other client library). On exit 8 `CONNECT_FAILED`, tell the user in one line and stop.

0. If the repo directory does not exist yet (an imported bot may have only the skills, not a git checkout), extract the source first. Live skill files live at `/home/box/agent-data/workflows/<id>/SKILL.md`. The source is in two skills: `telegram-recap-code` (the code, plus the stdlib extractor script) and `telegram-recap-code-tests` (the tests). Save the extractor from `telegram-recap-code` as `extract_code_skill.py`, then run `python3 extract_code_skill.py <telegram-recap-code SKILL.md> <telegram-recap-code-tests SKILL.md> telegram-recap-agent/`. The extractor writes every source file, sets `install.sh` executable, and checks each sha256 in both skills before writing anything; if a hash does not match, it fails with the path and stops. Then continue with install.
1. **Disclosure and Telegram API terms warning, before anything else** (before install, any card, or any credential). Send this to the user exactly (it is also what `$PY -m tg_recap consent show` prints):

   > ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
   >
   > Before you sign in: Telegram's API Terms of Service, section 1.5 (https://core.telegram.org/api/terms), say:
   > "you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."
   >
   > ChatBrief is an AI agent that reads your chats to write your recaps. Telegram may consider that against its API terms. Telegram's stated remedy for a breach is to notify the account responsible for the app, and if it isn't fixed within 10 days, to cut off that app's access to the Telegram API (your API ID). ChatBrief never trains on your chats or uses them to build any model. Use it at your own risk.
   >
   > To continue, confirm that you have read this and accept the risk.

   Ask them to reply with an explicit yes (for example "yes, I accept"). Anything else (silence, a question, "maybe", "later") is not consent: answer their question and stop; don't install or send any card. Never accept for them, and never treat this setup request itself as consent.
   After their explicit yes, install on your own computer, from the repo root. A venv is optional, not required:
   `./install.sh`
   That runs `"${PYTHON:-python3}" -m pip install --user -r requirements.txt`. If pip refuses because the environment is externally managed (PEP 668), it creates a local `.venv` and installs there instead. It prints the Python to use for every later command (the user's interpreter, or `.venv/bin/python` on fallback). Call that interpreter `$PY` below. You can also set `PYTHON` first (`PYTHON=python3 ./install.sh`).
   Then record the user's yes: `$PY -m tg_recap consent accept`. It stores only `tos_1_5_accepted_at` and `terms_version` in `~/.tg_recap/settings.json` (0600). Sign-in, `collect` and `run` exit 9 `CONSENT_REQUIRED` until this is done.
2. Tell the user, in plain words, the privacy lead-in from `telegram-recap-getting-started`, and that they need their own API ID and hash from https://my.telegram.org first.
3. Sign in with secret-request cards, one value per card. Each submitted card becomes an env var your Shell commands can read; you resume on a later turn after each one. Name each card's secret exactly as below. Every step exits with a code; follow the table.
   1. Card `TG_RECAP_API_ID` (API ID), then card `TG_RECAP_API_HASH` (API hash). Run `$PY -m tg_recap login --cards save-api`.
   2. Card `TG_RECAP_PHONE` (phone number, international format like +1...). Run `$PY -m tg_recap login --cards send-code`. Telegram sends a code to the user's Telegram app.
   3. Card `TG_RECAP_CODE` (the login code). Run `$PY -m tg_recap login --cards sign-in`. It reads `TG_RECAP_PHONE` again (the phone is never stored on disk), so that card must still be set.
   4. Only if sign-in exited 10: card `TG_RECAP_2FA` (two-step password). Run `$PY -m tg_recap login --cards password`.
   5. Confirm with `$PY -m tg_recap status --json` (`signed_in_files_present: true`).

   | Exit | Meaning | What you do |
   |---|---|---|
   | 0 | step done (after sign-in/password: signed in) | next step, or confirm with `status --json` |
   | 1 | failed (Telegram refused, kind only) | tell the user; offer `login --cards reset` and start again at 3.2 |
   | 2 | LOCK_HELD: a recap run is using the session | run the same step again in a minute |
   | 4 | FLOOD_STOP: Telegram asked to wait (pending cleared) | stop; try again from 3.2 later, never right away |
   | 5 | NOT_SET_UP: no API values saved | do 3.1 |
   | 6 | MISSING_DEPS | re-run the install in step 1 |
   | 9 | CONSENT_REQUIRED: the terms warning wasn't accepted | go back to step 1: show the warning, and run `consent accept` only after the user's explicit yes |
   | 8 | CONNECT_FAILED: couldn't reach Telegram's web endpoint (stderr names only the error type) | tell the user in one line and stop; try the same step again later. Don't change anything |
   | 10 | NEED_2FA | send the `TG_RECAP_2FA` card, then `password` |
   | 11 | CODE_INVALID | re-ask the `TG_RECAP_CODE` card, run `sign-in` again |
   | 12 | PASSWORD_INVALID | re-ask the `TG_RECAP_2FA` card, run `password` again |
   | 13 | CODE_EXPIRED (pending cleared) | start again at 3.2 (`send-code`), then a new `TG_RECAP_CODE` card |
   | 14 | PHONE_INVALID | re-ask the `TG_RECAP_PHONE` card, run `send-code` again |
   | 15 | API_INVALID | re-ask both API cards, run `save-api` again |
   | 16 | MISSING_ENV (stderr names the var) | send that card, run the same step again |
   | 17 | NO_PENDING (step out of order) | start again at 3.2 |

   `$PY -m tg_recap login --cards reset` wipes an unfinished sign-in (saved API values and any existing session stay). Plain `login` only prints these steps.

   After sign-in, the phone, code and two-step password stay saved as bot secrets; tell the user they can remove them in the app if they want.
4. Fallbacks (opt-in, only if cards can't be used):
   - Terminal: open a terminal window on your own desktop (for example `xfce4-terminal` or `x-terminal-emulator`), run `$PY -m tg_recap login --terminal` in it, and hand the desktop to the user with `request_box_help`. Don't watch, screenshot, or read the terminal while they type; confirm with `status --json`. Exits: 0 signed in, 1 not finished, 2 lock held, 4 flood stop.
   - Web page, only on a machine whose browser can open 127.0.0.1 pages: `$PY -m tg_recap login --web`. Don't change any browser or network policy to make it work.
5. Ask the frequency with a question widget: Daily (default), Every 4 hours, Every hour ("runs about 24 times a day and uses more of your Grok Bot plan"), Custom (whole hours, minimum 1). Ask the timezone only if they want something other than America/Los_Angeles.
6. Save it: `$PY -m tg_recap set-frequency <daily|every-4-hours|hourly|custom --hours N> [--timezone TZ] --json`. Use the `cron` and `timezone` it prints.
7. Create your own routine with that cron and timezone whose instruction is: follow the `telegram-recap-run` skill (it runs `$PY -m tg_recap collect` and writes the recap). Any test or first look before the schedule uses `$PY -m tg_recap collect --peek`, which doesn't advance the window or write `state.json`.
8. Show `$PY -m tg_recap sample` (synthetic example data) so they know what to expect, mention they can say "make it shorter" or "skip <chat>" any time, and say the first real recap comes at the next scheduled time.

**Change frequency:** ask with the step 5 widget (or take the owner's plain words), then run `$PY -m tg_recap set-frequency <daily|every-4-hours|hourly|custom --hours N> [--timezone TZ] --json` (or `$PY -m tg_recap settings set frequency <daily|every-4-hours|hourly|custom N>`; both save to `~/.tg_recap/settings.json`). Then update your own routine's cron and timezone to the printed values, and confirm in one line, e.g. "Done: recaps every 4 hours (0 */4 * * *, America/Los_Angeles)." Mention the plan warning if one is printed.

**Other recap settings** (length, muted/archived/DM chats, alert-bot feeds, per-chat include/skip/count-only, priority keywords): see "Settings from plain chat" in `telegram-recap-run`. `$PY -m tg_recap settings show` lists them without any IDs.

**Revoke / stop:** the user ends the session in Telegram **Settings > Devices**, and you pause or delete your routine. To fully remove local data, the user can delete `~/.tg_recap` on this computer (ask before deleting anything).

**If sign-in fails:** tell the user to check the values on my.telegram.org and run `login --cards reset` and step 3 again. Don't log in for them, don't debug their account, and don't promise support.

**Product name:** comes from `PRODUCT_NAME` in `tg_recap/branding.py`. Don't rename it yourself; if the owner picks a new name, it's edited there and applied with `python3 tools/apply_branding.py --from "<old name>"` plus `python3 tools/build_code_skill.py` in the repo (a code change, never done at runtime).
