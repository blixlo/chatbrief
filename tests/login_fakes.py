"""Offline stand-ins for Telethon's login errors. login_backend maps errors by
type name (as readonly.py does for FloodWaitError), so these need no network."""


class _TgErr(Exception):
    def __init__(self, *args):  # like Telethon, str() never includes request values
        super().__init__("The request was rejected (caused by a login request)")


class SessionPasswordNeededError(_TgErr):
    pass


class PhoneCodeInvalidError(_TgErr):
    pass


class PhoneCodeExpiredError(_TgErr):
    pass


class PasswordHashInvalidError(_TgErr):
    pass


class PhoneNumberInvalidError(_TgErr):
    pass


class FloodWaitError(_TgErr):
    def __init__(self, seconds):
        super().__init__()
        self.seconds = seconds
