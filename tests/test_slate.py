"""Tests for slate.py -- the per-pitcher forecasts for a day's games. No internet needed.

These use small hand-built inputs with known answers (so every expectation can be checked by hand):
league = 40,000 K / 180,000 PA = 22.22%, and each pitcher is 200 K in 800 batters faced = 25%.
"""

import pytest

import model
import slate

LEAGUE_K, LEAGUE_PA = 40000, 180000            # 22.22%
LEAGUE_RATE = LEAGUE_K / LEAGUE_PA


def pitcher(pid, name="Pitcher", k=200, bf=800):
    return {"id": pid, "name": name, "strikeouts": k, "batters_faced": bf, "games_started": 30, "games_pitched": 30}


def team(tid, k, pa=6000):
    return {"team_id": tid, "team_name": f"Team {tid}", "strikeouts": k, "plate_appearances": pa}


def batters(k, pa, count=9, start_id=1000):
    return {start_id + i: {"id": start_id + i, "name": f"Batter {i}", "strikeouts": k, "plate_appearances": pa} for i in range(count)}


def lineup(hitters):
    return [{"id": i, "name": h["name"]} for i, h in hitters.items()]


def game(pitcher_id=1, opp_lineup=None, state="Preview", status="Scheduled", opp_id=20):
    return {
        "game_pk": 1, "start": "2026-09-19T23:00:00Z", "status": status, "state": state,
        "away": {"team_id": 10, "team_name": "Team 10", "pitcher_id": pitcher_id, "pitcher_name": "Pitcher" if pitcher_id else None, "lineup": None},
        "home": {"team_id": opp_id, "team_name": f"Team {opp_id}", "pitcher_id": None, "pitcher_name": None, "lineup": opp_lineup},
    }


def run(games, pitchers=None, hitters=None, teams=None, logs=None, line=5.5):
    pitchers = pitchers if pitchers is not None else {1: pitcher(1)}
    teams = teams if teams is not None else {10: team(10, 1300), 20: team(20, 1300)}
    return slate.analyze_slate(games, pitchers, hitters or {}, teams, LEAGUE_K, LEAGUE_PA, logs or {}, line)


def away_row(rows):
    return next(r for r in rows if r["side"] == "away")


# ---------------------------------------------------------- lineup vs team

def test_a_posted_lineup_replaces_the_team_rate_with_the_pooled_lineup_rate():
    h = batters(k=150, pa=500)                                    # every batter 30%
    row = away_row(run([game(opp_lineup=lineup(h))], hitters=h))
    assert row["basis"] == "lineup"
    assert row["forecast"].matchup.opponent_rate == pytest.approx(0.30)
    assert row["lineup_rate"] == pytest.approx(0.30) and row["team_rate"] == pytest.approx(1300 / 6000)


def test_without_a_lineup_the_team_rate_is_used_and_labeled():
    row = away_row(run([game(opp_lineup=None)]))
    assert row["basis"] == "team" and row["lineup"] is None
    assert row["forecast"].matchup.opponent_rate == pytest.approx(1300 / 6000)


def test_a_lineup_with_too_few_batters_stats_falls_back_to_the_team_with_a_note():
    h = batters(k=150, pa=500, count=5)                          # only 5 of the 9 have stats
    lu = lineup(h) + [{"id": 9000 + i, "name": f"Rookie {i}"} for i in range(4)]
    row = away_row(run([game(opp_lineup=lu)], hitters=h))
    assert row["basis"] == "team"
    assert any("too few batters" in n for n in row["notes"])


def test_league_average_lineup_leaves_the_pitchers_own_forecast_unchanged():
    h = batters(k=200, pa=900)                                   # 22.22% = the league rate exactly
    fc = away_row(run([game(opp_lineup=lineup(h))], hitters=h))["forecast"]
    assert fc.adjustment_effect == pytest.approx(0.0, abs=1e-9)
    assert fc.expected == pytest.approx(fc.baseline_expected)


def test_strikeout_prone_bats_raise_the_forecast_and_contact_bats_lower_it():
    prone, contact = batters(k=180, pa=500), batters(k=80, pa=500)
    up = away_row(run([game(opp_lineup=lineup(prone))], hitters=prone))["forecast"]
    down = away_row(run([game(opp_lineup=lineup(contact))], hitters=contact))["forecast"]
    assert up.adjustment_effect > 0 > down.adjustment_effect
    assert up.expected > up.baseline_expected and down.expected < down.baseline_expected


def test_lineup_players_missing_from_the_stats_are_flagged_not_guessed():
    h = batters(k=150, pa=500, count=8)                          # 8 have stats, 1 call-up doesn't
    lu = lineup(h) + [{"id": 9999, "name": "Call-Up"}]
    row = away_row(run([game(opp_lineup=lu)], hitters=h))
    assert row["basis"] == "lineup"                              # 8 >= the 7 needed
    assert any("no stats this season yet" in n for n in row["notes"])
    assert [b["k_rate"] for b in row["lineup"]][-1] is None      # shown as "no stats yet", not a made-up rate


def test_low_sample_batters_are_flagged():
    h = batters(k=150, pa=500)
    h[1000] = {"id": 1000, "name": "Batter 0", "strikeouts": 5, "plate_appearances": 40}
    row = away_row(run([game(opp_lineup=lineup(h))], hitters=h))
    assert any("under 100 plate appearances" in n for n in row["notes"])
    assert row["lineup"][0]["low_sample"] is True


# ------------------------------------------------------- refusing to guess

def test_unannounced_pitcher_is_not_modeled_with_a_reason():
    rows = run([game(pitcher_id=None)])
    row = away_row(rows)
    assert not row["modeled"] and "not announced" in row["reason"] and row["pitcher"] == "TBD"


def test_pitcher_without_a_season_line_is_not_modeled():
    row = away_row(run([game(pitcher_id=777)]))
    assert not row["modeled"] and "No starts yet" in row["reason"]


def test_unknown_opponent_is_not_modeled_and_does_not_break_other_rows():
    rows = run([game(opp_id=99)], teams={10: team(10, 1300)})
    assert not away_row(rows)["modeled"] and "No batting data" in away_row(rows)["reason"]
    assert len(rows) == 2                                        # both sides still get a row


def test_zero_batters_faced_is_reported_not_crashed():
    rows = run([game()], pitchers={1: pitcher(1, k=0, bf=0)})
    assert not away_row(rows)["modeled"]


# ------------------------------------------------------------- workload

def test_workload_comes_from_the_last_five_starts_when_a_log_exists():
    log = {"rows": [{"batters_faced": b} for b in (10, 30, 25, 26, 24, 24, 26)]}
    row = away_row(run([game()], logs={1: log}))
    assert (row["workload"], row["workload_source"], row["starts_used"]) == (25, "api", 5)


def test_workload_without_a_log_is_a_labeled_manual_assumption():
    row = away_row(run([game()]))
    assert (row["workload"], row["workload_source"]) == (model.MANUAL_WORKLOAD, "manual")
    assert any("manual assumption" in n and "not from the API" in n for n in row["notes"])


def test_workload_is_kept_within_the_models_limits():
    short = {"rows": [{"batters_faced": 4}] * 5}
    assert away_row(run([game()], logs={1: short}))["workload"] == model.WORKLOAD_MIN


def test_small_sample_pitcher_is_flagged():
    row = away_row(run([game()], pitchers={1: pitcher(1, k=10, bf=44)}))
    assert any("Small sample" in n for n in row["notes"])


# --------------------------------------------------------- game state

@pytest.mark.parametrize("state, status, expected", [
    ("Preview", "Scheduled", True), ("Preview", "Pre-Game", True),
    ("Live", "In Progress", False), ("Final", "Final", False),
    ("Preview", "Postponed", False), ("Preview", "Cancelled", False), ("Preview", "Suspended: Rain", False),
])
def test_only_games_that_have_not_started_count_as_playable_previews(state, status, expected):
    assert slate.is_playable_preview({"state": state, "status": status}) is expected


# --------------------------------------------------------- matchup watch

def test_matchup_watch_ranks_by_effect_and_only_lists_games_not_yet_started():
    prone, contact, avg = batters(k=190, pa=500), batters(k=80, pa=500, start_id=2000), batters(k=200, pa=900, start_id=3000)
    hitters = {**prone, **contact, **avg}
    games = [
        {**game(opp_lineup=lineup(prone)), "game_pk": 1},
        {**game(opp_lineup=lineup(contact)), "game_pk": 2},
        {**game(opp_lineup=lineup(avg)), "game_pk": 3},                                        # effect exactly 0: in neither list
        {**game(opp_lineup=lineup(prone), state="Live", status="In Progress"), "game_pk": 4},  # already started: excluded
    ]
    helped, hurt = slate.matchup_watch(run(games, hitters=hitters))
    assert [r["game_pk"] for r in helped] == [1] and [r["game_pk"] for r in hurt] == [2]
    assert helped[0]["forecast"].adjustment_effect > 0 > hurt[0]["forecast"].adjustment_effect


def test_matchup_watch_orders_biggest_effect_first_and_respects_the_limit():
    games, hitters = [], {}
    for i, k in enumerate((120, 150, 190, 170), start=1):        # increasingly strikeout-prone lineups
        h = batters(k=k, pa=500, start_id=i * 1000)
        hitters.update(h)
        games.append({**game(opp_lineup=lineup(h)), "game_pk": i})
    helped, _ = slate.matchup_watch(run(games, hitters=hitters), top=2)
    effects = [r["forecast"].adjustment_effect for r in helped]
    assert len(helped) == 2 and effects == sorted(effects, reverse=True)
    assert [r["game_pk"] for r in helped] == [3, 4]
