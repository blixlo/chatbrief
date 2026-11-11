import os

import pytest

from tg_recap import config, paths
from tg_recap.config import Config


def test_default_is_daily_la():
    c = config.load()
    assert c.frequency == "daily" and c.timezone == "America/Los_Angeles"
    assert config.cron_for(c) == "0 8 * * *" and config.plan_warning(c) is None


@pytest.mark.parametrize("freq,hours,cron", [
    ("4h", None, "0 */4 * * *"), ("hourly", None, "0 * * * *"),
    ("custom", 1, "0 * * * *"), ("custom", 6, "0 */6 * * *"),
    ("custom", 24, "0 8 * * *"), ("custom", 48, "0 8 */2 * *"),
])
def test_cron_strings(freq, hours, cron):
    assert config.cron_for(Config(frequency=freq, custom_hours=hours)) == cron


def test_hourly_warning_text():
    assert config.plan_warning(Config(frequency="hourly")) == \
        "runs about 24 times a day and uses more of your Grok Bot plan"
    assert config.plan_warning(Config(frequency="custom", custom_hours=1)) == config.PLAN_WARNING
    assert config.plan_warning(Config(frequency="4h")) is None


@pytest.mark.parametrize("bad", [0, -3, 0.5])
def test_custom_floor_is_one_hour(bad):
    with pytest.raises(ValueError):
        Config(frequency="custom", custom_hours=bad).validate()


def test_save_load_roundtrip_and_perms(tg_home):
    config.save(Config(frequency="custom", custom_hours=3, timezone="Europe/Berlin"))
    c = config.load()
    assert (c.frequency, c.custom_hours, c.timezone) == ("custom", 3, "Europe/Berlin")
    assert oct(os.stat(paths.settings_file()).st_mode & 0o777) == "0o600"


def test_bad_timezone_rejected():
    with pytest.raises(Exception):
        Config(timezone="Not/AZone").validate()
