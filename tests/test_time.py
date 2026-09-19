"""Time zones. MLB's day and game times are Eastern, and a hosted server usually runs in UTC (or anywhere),
so the app must not depend on the machine's own clock or time zone."""

import os
import time
from datetime import date, datetime, timezone

import pytest

import api
import ui


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_mlb_today_follows_eastern_time_not_utc():
    # 10 PM Eastern on Sept 19 is already Sept 20 in UTC; MLB's "today" is still the 19th.
    assert api.mlb_today(utc(2026, 9, 20, 2, 0)) == date(2026, 9, 19)
    assert api.mlb_today(utc(2026, 9, 20, 5, 0)) == date(2026, 9, 20)      # 1 AM Eastern: a new day
    assert api.mlb_today(utc(2026, 12, 1, 4, 30)) == date(2026, 11, 30)    # winter, UTC-5: 11:30 PM Eastern


@pytest.mark.parametrize("start, shown", [
    ("2026-09-19T23:00:00Z", "7:00 PM"),      # daylight time (UTC-4)
    ("2026-12-01T00:30:00Z", "7:30 PM"),      # standard time (UTC-5), the evening before
    ("2026-09-19T17:05:00Z", "1:05 PM"),
    ("2026-09-19T14:10:00Z", "10:10 AM"),
])
def test_game_times_are_shown_in_eastern_time(start, shown):
    assert ui.game_time(start) == shown


@pytest.mark.parametrize("bad", [None, "", "not a date"])
def test_unreadable_start_times_show_nothing_instead_of_crashing(bad):
    assert ui.game_time(bad) == ""


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="changing the process time zone needs tzset (macOS/Linux)")
@pytest.mark.parametrize("machine_zone", ["UTC", "Asia/Tokyo", "America/Los_Angeles"])
def test_answers_do_not_change_with_the_machines_own_time_zone(machine_zone, monkeypatch):
    """The reason for all of this: a hosted server's clock must not change what visitors see."""
    monkeypatch.setenv("TZ", machine_zone)
    time.tzset()
    try:
        assert ui.game_time("2026-09-19T23:00:00Z") == "7:00 PM"
        assert api.mlb_today(utc(2026, 9, 20, 2, 0)) == date(2026, 9, 19)
    finally:
        monkeypatch.undo()
        time.tzset()
