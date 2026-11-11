# Sample recap, v0.1.5 (synthetic data only)

Everything below comes from the built-in fixture in `tg_recap/sample.py`: invented chat names ("Example ..."), invented people ("Sample Person A" ...), invented tokens (FAKEA, FAKEB). No real chats, people or messages were read. The window is the fixture's 24 hours ending Nov 11, 3:20 AM PT.

Regenerate the fallback part with: `python3 -m tg_recap sample`.

## 1. Agent-written recap (follows the `telegram-recap-run` writing rules)

This is what the agent writes from the `collect` JSON: needs-you first, plain sentences, no message dumps, no links or addresses, only the sender names shown in the chats.

```text
ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT

Needs you
• Sample Person A replied to you in Example Book Club and asked if you can pick the next book; they'd like it by Friday.
• Sample Person D mentioned you in Example Project Team and asked you to review the draft budget before the call.

Conversations
• Example Project Team: the team agreed to move the launch to next Tuesday so QA can finish. Sample Person D will update the timeline doc tonight; the rest was small copy edits.
• Example Book Club: November's meetup is set for the café on Thursday at 7 pm, and you offered to host in December.
• Example Markets Chat: the community call moved to Friday at 10 am. Nothing else was decided.

Alert feeds
• Whale Watch (example): 90 whale alerts, mostly FAKEA and FAKEB.

Also active: Example News Channel (6 new), Example Neighborhood (4 new).
5 other chats had no new messages.

Recap only, not financial advice.
```

## 2. Fallback formatter output (`python3 -m tg_recap run`, or `fallback_text` in the JSON)

Used when the agent can't write the recap. Deterministic and sentence-style.

```text
ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT

Needs you
• Sample Person A replied to you in Example Book Club: Can you also pick the next book?
• Sample Person D mentioned you in Example Project Team: Could you review the draft budget before the call?

Conversations
Example Project Team (9 new from Sample Person E and Sample Person D)
• Sample Person E said: Agreed to push the launch to next Tuesday so QA can finish.
• Sample Person D noted: I'll update the timeline doc tonight.
Example Book Club (3 new from Sample Person A, Sample Person B and Sample Person C)
• Sample Person B said: We'll go with the café on Thursday at 7 pm for November.
Example Markets Chat (3 new from Sample Person F and Sample Person G)
• Sample Person F noted: The community call moved to Friday 10 am.

Alert feeds
• Whale Watch (example): 90 whale alerts, mostly FAKEA and FAKEB.

Also active: Example News Channel (6 new), Example Neighborhood (4 new).
5 other chats had no new messages.

Recap only, not financial advice.
```
