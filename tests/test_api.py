"""Tests for api.py -- no internet needed.

The fixtures in tests/fixtures/ are REAL MLB Stats API responses (trimmed to a
few rows), so these tests check that our parsing matches the API's real shape.
The network layer is tested by swapping requests.get for a fake.
"""

import copy
import json
from pathlib import Path

import pytest
import requests

import api

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.load(open(FIXTURES / name, encoding="utf-8"))


# ------------------------------------------------------------- parsing

def test_team_batting_rows_have_the_fields_the_model_needs():
    rows = api.parse_team_batting(load("team_hitting_sample.json"), 2025)
    assert len(rows) == 3
    for row in rows:
        assert row["strikeouts"] > 0 and row["plate_appearances"] > row["strikeouts"]
        assert row["team_name"]


def test_team_with_missing_stats_stops_the_app_instead_of_biasing_the_league_average():
    payload = load("team_hitting_sample.json")
    del payload["stats"][0]["splits"][1]["stat"]["strikeOuts"]
    with pytest.raises(api.ApiError, match="missing"):
        api.parse_team_batting(payload, 2025)


def test_duplicate_team_rows_are_refused_not_double_counted():
    payload = load("team_hitting_sample.json")
    payload["stats"][0]["splits"].append(copy.deepcopy(payload["stats"][0]["splits"][0]))
    with pytest.raises(api.ApiError, match="twice"):
        api.parse_team_batting(payload, 2025)


@pytest.mark.parametrize("empty", [{}, {"stats": []}, {"stats": [{"splits": []}]}])
def test_empty_responses_become_clear_errors(empty):
    with pytest.raises(api.ApiError, match="no team batting data"):
        api.parse_team_batting(empty, 2030)
    with pytest.raises(api.ApiError, match="no pitcher data"):
        api.parse_pitchers(empty, 2030)


def test_traded_pitcher_appears_once_with_combined_totals():
    """Tyler Rogers: 10 K / 111 BF for the Mets + 38 K / 188 BF for the Giants = 48 K / 299 BF."""
    rows = api.parse_pitchers(load("pitchers_sample.json"), 2025)
    rogers = [r for r in rows if r["id"] == 643511]
    assert len(rogers) == 1
    assert (rogers[0]["strikeouts"], rogers[0]["batters_faced"]) == (48, 299)


def test_pitcher_rows_returned_twice_are_refused():
    payload = load("pitchers_sample.json")
    payload["stats"][0]["splits"].append(copy.deepcopy(payload["stats"][0]["splits"][0]))
    with pytest.raises(api.ApiError, match="twice"):
        api.parse_pitchers(payload, 2025)


def test_pitcher_without_batters_faced_is_skipped_but_others_survive():
    payload = load("pitchers_sample.json")
    del payload["stats"][0]["splits"][0]["stat"]["battersFaced"]
    rows = api.parse_pitchers(payload, 2025)
    assert len(rows) == len(payload["stats"][0]["splits"]) - 1


def test_game_log_of_a_starter_keeps_every_start_in_date_order():
    starts = api.parse_game_log(load("gamelog_starter.json"))
    assert len(starts) == 6
    assert [s["date"] for s in starts] == sorted(s["date"] for s in starts)
    assert all(s["batters_faced"] > 0 for s in starts)


def test_game_log_of_a_swingman_drops_relief_appearances():
    """AJ Blubaugh: 11 appearances in the real log, but only 3 were starts."""
    meta = load("swingman_meta.json")
    raw = load("gamelog_swingman.json")["stats"][0]["splits"]
    assert len(raw) > meta["starts"]                                   # the log really has relief outings in it
    starts = api.parse_game_log(load("gamelog_swingman.json"))
    assert len(starts) == meta["starts"] == 3


def test_game_log_with_no_data_is_an_empty_list_not_a_crash():
    assert api.parse_game_log({}) == []
    assert api.parse_game_log({"stats": []}) == []


def test_completed_season_logic():
    payload = {"seasons": [
        {"seasonId": "2024", "regularSeasonStartDate": "2024-03-28", "regularSeasonEndDate": "2024-09-30"},
        {"seasonId": "2025", "regularSeasonStartDate": "2025-03-18", "regularSeasonEndDate": "2025-09-28"},
        {"seasonId": "2026", "regularSeasonStartDate": "2026-03-25", "regularSeasonEndDate": "2026-09-27"},
        {"seasonId": "2027", "regularSeasonStartDate": "2027-03-25", "regularSeasonEndDate": "2027-09-26"},
    ]}
    result = api.parse_seasons(payload, today="2026-09-19")
    assert result["latest_completed"] == 2025            # 2026 hasn't finished yet
    assert result["in_progress"] == [2026]
    assert result["options"] == [2026, 2025, 2024]       # 2027 hasn't started, so it isn't offered
    assert api.parse_seasons(payload, today="2026-10-15")["latest_completed"] == 2026


# ------------------------------------------------------ schedule and hitters

def test_schedule_parses_the_real_shapes_including_partial_and_missing_lineups():
    meta = load("schedule_meta.json")
    games = {g["game_pk"]: g for g in api.parse_schedule(load("schedule_sample.json"))}
    assert len(games) == 4
    assert games[meta["final"]]["state"] == "Final"
    both = games[meta["both"]]
    assert len(both["away"]["lineup"]) == 9 and len(both["home"]["lineup"]) == 9
    assert both["away"]["pitcher_id"] and both["home"]["pitcher_name"]
    partial = games[meta["partial"]]                                    # only one side's lineup is posted
    posted, missing = meta["partial_side"], ("home" if meta["partial_side"] == "away" else "away")
    assert len(partial[posted]["lineup"]) == 9 and partial[missing]["lineup"] is None
    none = games[meta["none"]]
    assert none["away"]["lineup"] is None and none["home"]["lineup"] is None


def test_schedule_is_sorted_by_start_time():
    starts = [g["start"] for g in api.parse_schedule(load("schedule_sample.json"))]
    assert starts == sorted(starts)


@pytest.mark.parametrize("empty", [{}, {"dates": []}, {"dates": [{"games": []}]}])
def test_an_off_day_is_an_empty_list_not_an_error(empty):
    assert api.parse_schedule(empty) == []


def test_missing_probable_pitcher_and_broken_games_are_handled():
    payload = load("schedule_sample.json")
    game = payload["dates"][0]["games"][0]
    del game["teams"]["away"]["probablePitcher"]
    broken = copy.deepcopy(game)
    del broken["gamePk"]
    payload["dates"][0]["games"].append(broken)                          # a game with no ID is skipped, not fatal
    parsed = api.parse_schedule(payload)
    assert len(parsed) == 4
    tbd = next(g for g in parsed if g["game_pk"] == game["gamePk"])
    assert tbd["away"]["pitcher_id"] is None and tbd["away"]["pitcher_name"] is None


def test_hitters_skip_zero_plate_appearances_and_keep_a_traded_hitter_once():
    """Luis Arraez played for two teams: the API's single row already holds his combined 28 K / 635 PA."""
    meta = load("schedule_meta.json")
    rows = api.parse_hitters(load("hitters_sample.json"), 2026)
    assert all(r["plate_appearances"] > 0 for r in rows)
    arraez = [r for r in rows if r["name"] == "Luis Arraez"]
    assert len(arraez) == 1 and (arraez[0]["strikeouts"], arraez[0]["plate_appearances"]) == (meta["arraez"]["k"], meta["arraez"]["pa"])
    raw = load("hitters_sample.json")["stats"][0]["splits"]
    assert len(rows) < len(raw)                                          # the 0-PA rows were dropped


def test_duplicate_hitters_are_refused_and_empty_hitter_data_is_an_error():
    payload = load("hitters_sample.json")
    payload["stats"][0]["splits"].append(copy.deepcopy(payload["stats"][0]["splits"][0]))
    with pytest.raises(api.ApiError, match="twice"):
        api.parse_hitters(payload, 2026)
    with pytest.raises(api.ApiError, match="no hitter data"):
        api.parse_hitters({}, 2026)


# ------------------------------------------------------ network failures

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, bad_json=False):
        self.status_code, self._json, self._bad = status_code, json_data, bad_json
        self.ok = 200 <= status_code < 300
        self.url = "https://statsapi.mlb.com/api/v1/fake"

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._json


def fake_get(result):
    def _get(url, params=None, timeout=None):
        assert timeout, "every request must have a timeout"
        if isinstance(result, Exception):
            raise result
        return result
    return _get


@pytest.mark.parametrize("failure, expected_text", [
    (requests.Timeout(), "took longer"),
    (requests.ConnectionError(), "internet connection"),
    (FakeResponse(400, {"message": "Invalid season parameter: abc"}), "Invalid season parameter"),
    (FakeResponse(500), "HTTP 500"),
    (FakeResponse(200, bad_json=True), "valid JSON"),
])
def test_network_failures_become_friendly_errors(monkeypatch, failure, expected_text):
    monkeypatch.setattr(api.requests, "get", fake_get(failure))
    with pytest.raises(api.ApiError, match=expected_text):
        api._get_json("/anything", {})


def test_successful_request_returns_json_and_final_url(monkeypatch):
    monkeypatch.setattr(api.requests, "get", fake_get(FakeResponse(200, {"ok": True})))
    data, url = api._get_json("/anything", {})
    assert data == {"ok": True} and url.startswith("https://statsapi.mlb.com")


def test_missing_offline_snapshot_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "SNAPSHOT_DIR", tmp_path)                 # an empty folder: nothing saved
    with pytest.raises(api.ApiError, match="No offline snapshot"):
        api.load_snapshot()
    with pytest.raises(api.ApiError, match="2025 is missing"):
        api.load_snapshot(2025)


def test_saved_snapshots_are_found_newest_first_and_load_by_season():
    seasons = api.available_snapshot_seasons()
    assert seasons[:2] == [2026, 2025]
    assert api.load_snapshot()["season"] == 2026                        # no season given -> the newest one
    assert api.load_snapshot(2025)["season"] == 2025


def test_snapshot_records_whether_its_season_was_still_in_progress():
    assert api.load_snapshot(2026)["in_progress"] is True
    assert not api.load_snapshot(2025).get("in_progress")               # the 2025 file predates the flag; it was complete
