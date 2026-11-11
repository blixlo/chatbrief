"""The product name, in one place.

Telegram's API terms: the title must not include "Telegram" (2.3), users must be
told the app uses the Telegram API (2.2, see DISCLOSURE below), and no Telegram
logo or icon may be used (2.4). Change PRODUCT_NAME here, then run
`python3 tools/apply_branding.py --from "<old name>"` to update the README and
skill copies, and `python3 tools/build_code_skill.py` to rebuild the code skills.
tests/test_branding.py fails if any user-facing text still uses another name.
"""
PRODUCT_NAME = "ChatBrief"

# Shown verbatim in docs, skills, both sign-in screens and at the top of the 1.5 warning.
DISCLOSURE = (f"{PRODUCT_NAME} is an unofficial app that works alongside Telegram. It uses the Telegram API "
              "and is not affiliated with or endorsed by Telegram.")
