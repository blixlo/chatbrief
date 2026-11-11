import pytest

from tg_recap.redact import redact

# All values below are made up for the test.
CASES = [
    ("buy 0x1111111111111111111111111111111111111111 now", "0x1111111111111111111111111111111111111111"),
    ("ca: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"),
    ("send to bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"),
    ("join https://t.me/+AbCdEfGhIjK123", "t.me/+AbCdEfGhIjK123"),
    ("old link t.me/joinchat/AAAAAEfake", "joinchat"),
    ("call me +1 555 010 9999", "555 010 9999"),
    ("or (555) 010-9999 tonight", "010-9999"),
    ("chat -1001234567890 has it", "1001234567890"),
    ("user 987654321 said hi", "987654321"),
]


@pytest.mark.parametrize("text,gone", CASES)
def test_redaction(text, gone):
    out = redact(text)
    assert gone not in out
    assert "removed]" in out


def test_ordinary_text_kept():
    t = "Meet Friday 7 pm, budget 1,500,000 and date 2026-11-10, price $42.50"
    assert redact(t) == t


def test_login_codes_and_secrets_stripped():
    # Synthetic only: these are not real credentials.
    cases = [
        ("Telegram said Login code: 12345. Do not share it.", "12345"),
        ("your verification code is 482910", "482910"),
        ("OTP: 998877", "998877"),
        ("code: 12345 sits here", "12345"),
        ("password: hunter2-example", "hunter2-example"),
        ("seed phrase: alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima",
         "alpha bravo charlie"),
    ]
    for text, gone in cases:
        out = redact(text)
        assert gone not in out, (text, out)
        assert "removed]" in out


def test_ordinary_numbers_and_dates_kept():
    t = "Meet Friday 7 pm, budget 1,500,000 and date 2026-11-10, price $42.50"
    assert redact(t) == t
    assert "12345" in redact("the room number is 12345 today")


def test_tracking_query_and_x_status_links_stripped():
    url = "https://example.com/post?a=secrettrack&s=20"
    assert redact(url) == "https://example.com/post"
    assert "secrettrack" not in redact("see " + url)
    xurl = "https://x.com/someone/status/1234567890123456789?a=track&s=20"
    out = redact("posted " + xurl)
    assert "1234567890123456789" not in out and "track" not in out and "x.com" not in out
    assert "[link removed]" in out
    leftover = "see [id removed]?a=track&s=20 end"
    assert "track" not in redact(leftover) and "?a=" not in redact(leftover)
