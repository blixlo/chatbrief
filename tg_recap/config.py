"""User settings in ~/.tg_recap/settings.json (0600, folder 0700).

Validated against SCHEMA with defaults. Older installs kept frequency and
timezone in config.json; it is read once as a fallback when settings.json is
missing. Chat rules are stored by internal chat key (a salted hash, never a
Telegram ID) with the title shown to you.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from . import paths

FREQUENCIES = ("daily", "4h", "hourly", "custom")
LENGTHS = ("short", "standard", "detailed")
CHAT_RULES = ("include", "skip", "count-only")
DEFAULT_TZ = "America/Los_Angeles"
MIN_HOURS = 1
MAX_KEYWORDS = 30
PLAN_WARNING = "runs about 24 times a day and uses more of your Grok Bot plan"

# Caps per length: chars per message, messages per chat, total chars across chats,
# chats shown, and fallback bullets per chat.
LENGTH_CAPS = {
    "short": {"msg_chars": 200, "chat_msgs": 15, "total_chars": 6000, "max_chats": 6, "bullets": 1},
    "standard": {"msg_chars": 300, "chat_msgs": 30, "total_chars": 15000, "max_chats": 10, "bullets": 2},
    "detailed": {"msg_chars": 500, "chat_msgs": 60, "total_chars": 40000, "max_chats": 20, "bullets": 3},
}

# field -> (type, description). Used for validation and `settings show`.
SCHEMA = {
    "frequency": (str, "daily | 4h | hourly | custom (stored for the schedule)"),
    "custom_hours": ((int, type(None)), "whole hours >= 1, only for custom"),
    "daily_hour": (int, "local hour 0-23 for daily recaps"),
    "timezone": (str, "IANA zone, e.g. America/Los_Angeles"),
    "include_muted": (bool, "muted chats appear under Also active"),
    "include_archived": (bool, "archived chats are read"),
    "include_dms": (bool, "one-to-one chats are read"),
    "length": (str, "short | standard | detailed"),
    "priority_keywords": (list, "words flagged first"),
    "collapse_alert_bots": (bool, "alert-bot feeds collapse to one line"),
    "chat_rules": (dict, "chat key -> {title, rule: include | skip | count-only}"),
    "memecoin_buy_sol": ((int, float), "reported SOL buy threshold (default 10)"),
    "memecoin_buy_usd": ((int, float), "reported USD buy threshold (default 2000)"),
    "memecoin_ticker_stop": (list, "extra tickers to ignore in Memecoin mentions"),
    "memecoin_show_ca": (bool, "show public token CAs in Memecoin mentions (default on)"),
}


class SettingsError(ValueError):
    pass


@dataclass
class Config:
    frequency: str = "daily"
    custom_hours: int | None = None
    daily_hour: int = 8
    timezone: str = DEFAULT_TZ
    include_muted: bool = True
    include_archived: bool = False
    include_dms: bool = True
    length: str = "standard"
    priority_keywords: list = field(default_factory=list)
    collapse_alert_bots: bool = True
    chat_rules: dict = field(default_factory=dict)
    memecoin_buy_sol: float = 10.0
    memecoin_buy_usd: float = 2000.0
    memecoin_ticker_stop: list = field(default_factory=list)
    memecoin_show_ca: bool = True

    def validate(self) -> "Config":
        for name, (typ, _desc) in SCHEMA.items():
            value = getattr(self, name)
            if typ is int and isinstance(value, bool) or not isinstance(value, typ):
                raise SettingsError(f"{name} has the wrong type")
        if self.frequency not in FREQUENCIES:
            raise SettingsError(f"frequency must be one of {', '.join(FREQUENCIES)}")
        if self.frequency == "custom":
            if self.custom_hours is None:
                raise SettingsError("custom frequency needs --hours")
            self.custom_hours = normalize_hours(self.custom_hours)
        else:
            self.custom_hours = None
        if not 0 <= int(self.daily_hour) <= 23:
            raise SettingsError("daily hour must be 0-23")
        try:
            ZoneInfo(self.timezone)
        except Exception:  # noqa: BLE001
            raise SettingsError("timezone must be an IANA zone like America/Los_Angeles") from None
        if self.length not in LENGTHS:
            raise SettingsError(f"length must be one of {', '.join(LENGTHS)}")
        kws = []
        for k in self.priority_keywords:
            if not isinstance(k, str) or not k.strip() or len(k) > 40:
                raise SettingsError("priority keywords must be short words or phrases")
            if k.strip().casefold() not in {x.casefold() for x in kws}:
                kws.append(k.strip())
        if len(kws) > MAX_KEYWORDS:
            raise SettingsError(f"at most {MAX_KEYWORDS} priority keywords")
        self.priority_keywords = kws
        for key, rule in self.chat_rules.items():
            if not isinstance(key, str) or not isinstance(rule, dict) or rule.get("rule") not in CHAT_RULES \
                    or not isinstance(rule.get("title"), str):
                raise SettingsError("chat_rules entries need a title and a rule (include, skip, count-only)")
        for name in ("memecoin_buy_sol", "memecoin_buy_usd"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SettingsError(f"{name} has the wrong type")
            if value < 0:
                raise SettingsError(f"{name} must be 0 or more")
            setattr(self, name, float(value))
        stops = []
        for k in self.memecoin_ticker_stop:
            if not isinstance(k, str) or not k.strip() or len(k) > 16:
                raise SettingsError("memecoin ticker stop entries must be short tickers")
            tok = k.strip().lstrip("$").upper()
            if tok not in stops:
                stops.append(tok)
        if len(stops) > MAX_KEYWORDS:
            raise SettingsError(f"at most {MAX_KEYWORDS} extra memecoin stop tickers")
        self.memecoin_ticker_stop = stops
        return self

    @property
    def interval_hours(self) -> int:
        return {"daily": 24, "4h": 4, "hourly": 1}.get(self.frequency) or int(self.custom_hours)

    @property
    def caps(self) -> dict:
        return LENGTH_CAPS[self.length]

    def rule_for(self, key: str) -> str | None:
        r = self.chat_rules.get(key)
        return r["rule"] if r else None


def normalize_hours(hours) -> int:
    h = int(hours)
    if float(hours) != h:
        raise SettingsError("custom interval must be a whole number of hours")
    if h < MIN_HOURS:
        raise SettingsError(f"custom interval must be at least {MIN_HOURS} hour")
    return h


def _from_dict(data: dict) -> Config:
    known = {k: v for k, v in (data or {}).items() if k in Config.__dataclass_fields__}
    try:
        return Config(**known).validate()
    except TypeError:
        raise SettingsError("settings.json has an unexpected shape") from None


def load() -> Config:
    data = paths.read_json(paths.settings_file())
    if data is not None and not isinstance(data, dict):
        raise SettingsError("settings.json has an unexpected shape")
    if not any(k in Config.__dataclass_fields__ for k in (data or {})):
        # legacy config.json keeps frequency/timezone; also when settings.json holds only the consent record
        legacy = paths.read_json(paths.config_file(), {}) or {}
        data = {**(legacy if isinstance(legacy, dict) else {}), **(data or {})}
    return _from_dict(data)


def save(cfg: Config) -> None:
    """Write settings; the consent record (consent.KEYS) already in the file is kept."""
    from .consent import preserved
    cfg.validate()
    paths.write_json(paths.settings_file(), {**asdict(cfg), **preserved()})


def cron_for(cfg: Config) -> str:
    """Cron string (in cfg.timezone) for the routine that runs the recap.

    custom N hours: N < 24 -> "0 */N * * *" (cron restarts the count at midnight
    when 24 is not a multiple of N); N >= 24 -> every round(N/24) days at daily_hour.
    """
    cfg.validate()
    if cfg.frequency == "daily":
        return f"0 {cfg.daily_hour} * * *"
    if cfg.frequency == "4h":
        return "0 */4 * * *"
    if cfg.frequency == "hourly":
        return "0 * * * *"
    n = cfg.custom_hours
    if n == 1:
        return "0 * * * *"
    if n < 24:
        return f"0 */{n} * * *"
    days = max(1, round(n / 24))
    return f"0 {cfg.daily_hour} * * *" if days == 1 else f"0 {cfg.daily_hour} */{days} * *"


def plan_warning(cfg: Config) -> str | None:
    """Warning shown by the frequency picker; None when the choice is light."""
    cfg.validate()
    n = cfg.interval_hours
    if n == 1:
        return PLAN_WARNING
    if n < 4:
        return f"runs about {24 // n} times a day and uses more of your Grok Bot plan"
    return None
