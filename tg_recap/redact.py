"""Strip identifiers and secrets from text before it leaves the collector.

Removed: contract/wallet-looking strings (EVM 0x..., Solana/base58, Bitcoin),
long hex blobs, t.me / telegram.me links (incl. invite links), x.com/twitter
status links, URL query/fragment strings, phone numbers, numeric Telegram IDs,
login/verification codes, passwords, and seed/recovery phrases.
"""
from __future__ import annotations

import re

_X_STATUS = re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/[^\s/]+/status/\S+", re.I)
_URL = re.compile(r"https?://[^\s<>]+", re.I)
_QUERY_AFTER_REDACT = re.compile(r"\[(?:id|address|link) removed\][?#]\S+")
_SECRETS = [
    (re.compile(
        r"\b(?:seed\s*phrase|recovery\s*phrase|secret\s*phrase|mnemonic(?:\s*phrase)?)"
        r"\s*[:=]?\s*(?:\S+\s+){11,23}\S+",
        re.I,
    ), "[seed phrase removed]"),
    (re.compile(r"\b(?:password|passwd|passphrase)\s*[:=]\s*\S+", re.I), "[password removed]"),
    (re.compile(
        r"(?:(?:login|verification|authentication|auth|one[-\s]*time)\s+)(?:codes?|otp)"
        r"\s*[:=]?\s*\d{4,8}"
        r"|\b(?:login|verification|authentication|auth)\s+codes?\b(?:\s+\w+){0,3}\s*[:=]?\s*\d{4,8}"
        r"|\b(?:codes?|otp)\s*[:=]\s*\d{4,8}"
        r"|\b\d{5,6}\b(?=(?:\s+\w+){0,4}\s*(?:login\s+)?(?:codes?|otp|verification))"
        r"|(?:(?:login\s+)?(?:codes?|otp|verification))(?:\s+\w+){0,3}\s*[:=]?\s*\d{5,6}\b",
        re.I,
    ), "[code removed]"),
]
_PATTERNS = [
    (re.compile(r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/\S+", re.I), "[link removed]"),
    (re.compile(r"tg://\S+", re.I), "[link removed]"),
    (re.compile(r"\b0x[a-fA-F0-9]{40,64}\b"), "[address removed]"),
    (re.compile(r"\bbc1[a-z0-9]{25,60}\b", re.I), "[address removed]"),
    (re.compile(r"\b(?=[1-9A-HJ-NP-Za-km-z]*\d)(?=[1-9A-HJ-NP-Za-km-z]*[A-Za-z])[1-9A-HJ-NP-Za-km-z]{32,44}\b"), "[address removed]"),
    (re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"), "[address removed]"),
    (re.compile(r"\b[a-fA-F0-9]{48,}\b"), "[address removed]"),
    (re.compile(r"\+\d[\d\s().-]{6,}\d"), "[phone removed]"),
    (re.compile(r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"), "[phone removed]"),
    (re.compile(r"(?<![\d.,])-?\d{7,}(?![\d.,]*\d)"), "[id removed]"),
]


def _strip_urls(text: str) -> str:
    text = _X_STATUS.sub("[link removed]", text)
    return _URL.sub(lambda m: re.split(r"[?#]", m.group(0), maxsplit=1)[0], text)


def redact(text: str) -> str:
    if not text:
        return ""
    out = _strip_urls(text)
    for pattern, repl in _SECRETS + _PATTERNS:
        out = pattern.sub(repl, out)
    return _QUERY_AFTER_REDACT.sub("[link removed]", out)


_ADDRESSY = re.compile(r"\b0x[a-fA-F0-9]{40}\b|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def looks_like_address(text: str) -> bool:
    return bool(text and _ADDRESSY.search(text))
