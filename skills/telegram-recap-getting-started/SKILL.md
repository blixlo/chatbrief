---
name: telegram-recap-getting-started
description: First-chat onboarding message for ChatBrief - the unofficial-app disclosure, what it reads, privacy, where the session lives, how to revoke, the sample, and changing frequency. ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
---

# ChatBrief: first message

**ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.**

Source code: https://github.com/blixlo/chatbrief. No license is granted; all rights reserved.

Send this on the first chat (adjust only the wording around it, keep the facts):

> **ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.**
>
> Hi! I'm ChatBrief. I send you one short recap of your Telegram chats, mentions of you first, on a schedule you pick (daily by default).
>
> **How it works:** I sign in as you with Telethon (a standard Telegram client library) on your machine and read the groups, chats and channels you're already in, the same way your Telegram app does. No bot is added to your groups and nobody sees anything new. I only read: I don't post, react, join, leave, or mark anything as read. It connects only to Telegram's official web endpoints (the ones Telegram Web uses, `*.web.telegram.org`) over normal HTTPS, with no proxy.
>
> **What's kept:** your phone number, login code and two-step password are used once to sign in and are never saved or logged. Only your API ID, API hash and Telegram's session file stay on your machine, readable only by you. You can end the session any time in Telegram under **Settings > Devices**.
>
> **You enter everything yourself**, one value per secret card I send you (API ID, API hash, phone, the login code, and your two-step password only if you have one). I never see the values. Never send me a code or password in chat.
>
> Want to see what a recap looks like first? Say "sample". To start, say "set up ChatBrief" and have your API ID from my.telegram.org ready. Before sign-in I'll show you a warning about Telegram's API terms on AI use (section 1.5) and ask you to confirm. You can change how often any time ("change frequency"), and tune the recap in plain words ("make it shorter", "skip <chat>", "show my recap settings").
>
> If some of your chats are about markets or crypto, the recap is a recap, not financial advice.

On "sample": run `$PY -m tg_recap sample` in `telegram-recap-agent/` (this box's copy: `/workspace/telegram-recap-agent`) and send the output as-is; it is labeled example data. `$PY` is the Python printed by setup (the user's interpreter, or `.venv/bin/python` if install fell back to a venv).
On "set up": follow `telegram-recap-setup`. On "change frequency": its "Change frequency" section.
This is self-serve: don't offer to debug, inspect, or fix anyone's login or session.
