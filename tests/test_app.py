"""Tests that run the real pages with Streamlit's headless test runner.

Almost all use Offline demo mode (the saved real-API snapshot), so they need no
internet and give the same answer every time. `start_on(page)` starts the app
directly on one page, because the test runner can't click navigation links.
"""

import copy

import pytest
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

import api
import slate

LEAGUE = "League average (no opponent effect)"


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_data.clear()      # so one test's cached data can't leak into the next
    yield


def start_on(page, offline=True, season=2025, **session_state):
    """Run the app on `page` ("home", "browse", "lab", "about"), optionally preselecting things.

    Offline runs use the saved 2025 snapshot unless told otherwise (season=None picks the newest saved one),
    because the tests below check exact 2025 numbers."""
    script = f"""
import context, navigation, state, ui
import streamlit as st
st.set_page_config(layout="wide")
ui.inject_css()
state.init()
ctx = context.setup()
navigation.run(ctx, start="{page}")
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.session_state["offline_mode"] = offline      # set BEFORE the first run, so offline tests never touch the network
    if offline and season is not None:
        at.session_state["offline_season"] = season
    for key, value in session_state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def snapshot_pitcher(name_prefix):
    snap = api.load_snapshot(2025)
    return next(p for p in snap["pitchers"]["rows"] if p["name"].startswith(name_prefix))


def metrics(at):
    return {m.label: m for m in at.metric}


def text(at):
    return " ".join(e.value for e in list(at.markdown) + list(at.caption) + list(at.info) + list(at.warning))


# ------------------------------------------------------------------ home

def test_home_page_shows_the_mission_and_no_forecast():
    at = start_on("home")
    assert "Our mission" in text(at)
    assert not at.metric                       # nobody is shown a matchup they didn't choose
    assert any("OFFLINE DEMO MODE" in w.value for w in at.warning)


def test_home_lists_the_top_strikeout_pitchers_as_buttons():
    at = start_on("home")
    labels = [b.label for b in at.button]
    assert labels.count("Forecast →") == 6
    assert "Browse pitchers" in labels and "Open the Forecast Lab" in labels and "Today's games" in labels
    assert "Garrett Crochet" in text(at)       # the 2025 strikeout leader in the saved snapshot


def test_offline_mode_makes_no_network_requests(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Offline mode must not touch the network")
    monkeypatch.setattr(api.requests, "get", no_network)
    for page in ("home", "browse", "lab"):
        start_on(page)


# ---------------------------------------------------------------- browse

def test_browse_lists_pitchers_and_search_narrows_them():
    at = start_on("browse")
    assert "Showing 184 of 369 starting pitchers" in text(at)          # default: 10+ starts
    at.text_input(key="browse_query").set_value("Skubal").run()
    assert "Showing 1 of 369" in text(at)
    at.text_input(key="browse_query").set_value("zzzzzz").run()
    assert any("No pitchers match" in i.value for i in at.info)


def test_browse_sample_size_filter_changes_the_count():
    at = start_on("browse")
    at.selectbox(key="browse_size").select("All starters").run()
    assert "Showing 369 of 369" in text(at)
    at.selectbox(key="browse_size").select("20+ starts").run()
    assert "Showing 184" not in text(at) and "of 369" in text(at)


# ------------------------------------------------------------------- lab

def test_lab_opened_cold_is_empty_and_guides_the_user():
    at = start_on("lab")
    assert "Start by choosing a pitcher" in text(at)
    assert not at.metric and not at.error                # no random pitcher line, no results
    assert at.selectbox(key="w_pitcher").value is None and at.selectbox(key="w_opp").value is None


def test_example_button_fills_in_a_matchup():
    at = start_on("lab")
    next(b for b in at.button if b.label.startswith("Just show me an example")).click().run()
    assert {"Expected strikeouts", "Over 5.5", "Under 5.5", "Central 80% interval"} <= set(metrics(at))


def test_choosing_only_a_pitcher_asks_for_an_opponent_instead_of_guessing():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid)
    assert any("choose an opponent" in i.value for i in at.info)
    assert not at.metric


def test_full_selection_gives_a_forecast_with_an_api_derived_workload():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp="Arizona Diamondbacks")
    assert set(metrics(at)) == {"Expected strikeouts", "Over 5.5", "Under 5.5", "Central 80% interval"}
    assert "average of the pitcher's last 5 starts" in text(at)
    assert at.slider[0].value == 25                       # Crochet's last five starts: 26, 24, 24, 25, 26
    assert "Our mission" not in text(at)


def test_dragging_the_slider_changes_the_forecast_in_the_right_direction():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp="Arizona Diamondbacks")
    at.slider[0].set_value(15).run()
    low = float(metrics(at)["Expected strikeouts"].value)
    at.slider[0].set_value(30).run()
    assert float(metrics(at)["Expected strikeouts"].value) > low


def test_league_average_opponent_shows_no_adjustment():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp=LEAGUE)
    assert metrics(at)["Expected strikeouts"].delta.startswith("+0.00")


def test_line_that_is_not_a_half_integer_shows_an_error_and_no_forecast():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp=LEAGUE)
    at.number_input(key="w_line").set_value(5.0).run()
    assert any("half-integer" in e.value for e in at.error)
    assert not at.metric                                  # nothing is shown rather than a wrong number
    at.number_input(key="w_line").set_value(4.5).run()
    assert not at.error and "Over 4.5" in metrics(at)


def test_pitcher_without_a_saved_game_log_uses_a_clearly_labeled_manual_workload():
    pid = snapshot_pitcher("Nathan Eovaldi")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp=LEAGUE)
    assert "manual assumption" in text(at) and "not derived from the API" in text(at)
    assert at.slider[0].value == 24


def test_small_sample_pitcher_gets_a_warning():
    pid = snapshot_pitcher("Albert Su")["id"]             # real snapshot data: 44 batters faced
    at = start_on("lab", sel_pitcher=pid, sel_opp=LEAGUE)
    assert any("Small sample" in w.value for w in at.warning)


def test_clamped_probability_shows_a_notice(monkeypatch):
    """No real 2025 starter triggers the clamp, so this uses ONE synthetic pitcher (0 K in 150 BF)."""
    real = api.load_snapshot(2025)

    def patched(season=None):
        snap = copy.deepcopy(real)
        snap["pitchers"]["rows"].append(
            {"id": 999999, "name": "Synthetic Test Pitcher", "strikeouts": 0, "batters_faced": 150,
             "games_started": 1, "games_pitched": 1})
        return snap
    monkeypatch.setattr(api, "load_snapshot", patched)
    at = start_on("lab", sel_pitcher=999999, sel_opp=LEAGUE)
    assert any("Probability clamped" in w.value for w in at.warning)


def test_a_remembered_pitcher_missing_from_the_season_is_cleared_not_a_crash():
    at = start_on("lab", sel_pitcher=123456789, sel_opp=LEAGUE)      # not a real pitcher ID
    assert not at.exception and not at.metric
    assert at.session_state["sel_pitcher"] is None


def test_model_explanation_includes_assumptions_and_data_sources():
    pid = snapshot_pitcher("Garrett Crochet")["id"]
    at = start_on("lab", sel_pitcher=pid, sel_opp="Arizona Diamondbacks")
    assert [e.label for e in at.expander] == ["How this model works"]
    body = " ".join(m.value for m in at.expander[0].markdown)
    assert "Untested matchup formula" in body and "fetched" in body and "Pitcher-only baseline" in body


# ------------------------------------------------- home page: the interactive parts

def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def snapshot_league_and_teams():
    teams = api.load_snapshot(2026)["teams"]["rows"]
    k, pa = sum(t["strikeouts"] for t in teams), sum(t["plate_appearances"] for t in teams)
    return k, pa, teams


def test_home_stat_tiles_show_the_real_league_numbers():
    at = start_on("home", season=2026)
    k, pa, teams = snapshot_league_and_teams()
    top = max(api.load_snapshot(2026)["pitchers"]["rows"], key=lambda p: p["strikeouts"])
    body = text(at)
    assert f"{k / pa:.1%}" in body and f"{k:,}" in body
    assert top["name"] in body and f"{top['strikeouts']} strikeouts" in body


def test_home_try_it_starts_empty_and_needs_both_a_pitcher_and_a_team():
    at = start_on("home", season=2026)
    assert at.selectbox(key="home_pitcher").value is None and at.selectbox(key="home_opp").value is None
    assert not at.metric and any("Choose a pitcher and an opponent" in i.value for i in at.info)
    click(at, max(api.load_snapshot(2026)["pitchers"]["rows"], key=lambda p: p["strikeouts"])["name"])
    assert not at.metric                                               # a pitcher alone is not enough


def test_home_quick_picks_build_a_forecast_and_the_opponent_changes_it():
    at = start_on("home", season=2026)
    click(at, max(api.load_snapshot(2026)["pitchers"]["rows"], key=lambda p: p["strikeouts"])["name"])
    click(at, "Strikeout-heavy team")
    assert set(metrics(at)) == {"Expected strikeouts", "Chance of over 5.5"}
    heavy = float(metrics(at)["Expected strikeouts"].value)
    click(at, "Contact-heavy team")
    contact = float(metrics(at)["Expected strikeouts"].value)
    assert heavy > contact + 0.5                                          # the same pitcher, a much tougher opponent


def test_home_try_it_gives_exactly_the_same_answer_as_the_forecast_lab():
    """Two places must never disagree about the same matchup."""
    snap = api.load_snapshot(2026)
    top = max(snap["pitchers"]["rows"], key=lambda p: p["strikeouts"])
    _, _, teams = snapshot_league_and_teams()
    heavy = max(teams, key=lambda t: t["strikeouts"] / t["plate_appearances"])["team_name"]
    home = start_on("home", season=2026)
    click(home, top["name"])
    click(home, "Strikeout-heavy team")
    lab = start_on("lab", season=2026, sel_pitcher=top["id"], sel_opp=heavy)
    assert metrics(home)["Expected strikeouts"].value == metrics(lab)["Expected strikeouts"].value
    assert metrics(home)["Chance of over 5.5"].value == metrics(lab)["Over 5.5"].value


def test_home_leaders_chart_toggles_between_pitchers_and_offenses():
    at = start_on("home", season=2026)
    assert any("highest strikeout rates" in c.value for c in at.caption)
    at.segmented_control(key="home_leaders").set_value("Offenses").run()
    assert any("offenses that strike out most often" in c.value for c in at.caption)
    assert not at.exception


def test_home_slate_teaser_shows_the_saved_slate_offline():
    at = start_on("home", season=2026)
    games = api.load_snapshot(2026)["schedule"]["games"]
    playable = sum(1 for g in games if slate.is_playable_preview(g))
    body = text(at)
    assert f"{len(games)} games · {playable} still to play" in body and "Saved slate" in body
    assert any("See which bats could help or hurt each pitcher" in b.label for b in at.button)


def test_home_has_no_slate_teaser_for_a_snapshot_without_a_slate():
    at = start_on("home", season=2025)
    assert "still to play" not in text(at) and not at.error


def test_home_slate_teaser_disappears_quietly_if_the_schedule_cannot_load(monkeypatch):
    _live_with_snapshot_data(monkeypatch)
    monkeypatch.setattr(api, "fetch_schedule", lambda day: (_ for _ in ()).throw(api.ApiError("down")))
    at = start_on("home", offline=False)
    assert "Our mission" in text(at) and "still to play" not in text(at) and not at.error


def test_home_slate_teaser_is_hidden_on_an_off_day(monkeypatch):
    _live_with_snapshot_data(monkeypatch)
    monkeypatch.setattr(api, "fetch_schedule", lambda day: {"date": day, "games": [], "fetched_at": "t", "source": "t"})
    at = start_on("home", offline=False)
    assert "still to play" not in text(at) and not at.error


# ------------------------------------------------------------ seasons

def test_offline_mode_opens_on_the_newest_saved_season_and_flags_it_as_in_progress():
    at = start_on("home", season=None)
    newest = api.available_snapshot_seasons()[0]
    assert newest == 2026
    assert any(f"saved data from the {newest} season" in w.value for w in at.warning)
    assert any("still in progress" in i.value for i in at.info)
    assert f"{newest} season (in progress)" in text(at)
    assert f"Top strikeout pitchers of {newest} so far" in text(at)


def test_a_completed_season_is_not_labeled_in_progress():
    at = start_on("home", season=2025)
    assert not any("still in progress" in i.value for i in at.info)
    assert "Top strikeout pitchers of 2025" in text(at) and "so far" not in text(at)


def test_live_mode_opens_on_the_current_season_not_the_last_completed_one(monkeypatch):
    """The season list is newest first; 2026 is in progress and 2025 is the latest completed one."""
    snap = api.load_snapshot(2026)
    monkeypatch.setattr(api, "fetch_seasons", lambda: {
        "latest_completed": 2025, "options": [2026, 2025], "in_progress": [2026],
        "fetched_at": "test", "source": "test"})
    monkeypatch.setattr(api, "fetch_team_batting", lambda season: snap["teams"])
    monkeypatch.setattr(api, "fetch_pitchers", lambda season: snap["pitchers"])
    monkeypatch.setattr(api, "fetch_schedule", lambda day: {**snap["schedule"], "date": day})   # the home page's slate teaser
    at = start_on("home", offline=False)
    assert at.sidebar.selectbox[0].value == 2026
    assert any("still in progress" in i.value for i in at.info)


# ----------------------------------------------------------------- today

def slate_table(at):
    """The big 'All probable starters' table (the last table on the page)."""
    return at.dataframe[-1].value


def test_today_page_explains_what_it_is_and_shows_the_saved_slate():
    at = start_on("today", season=2026)
    body = text(at)
    assert "has no sportsbook lines" in body and "Matchup watch" in body and "All probable starters" in body
    games = api.load_snapshot(2026)["schedule"]["games"]
    posted = sum(1 for g in games for side in ("away", "home") if g[side]["lineup"])
    assert f"**{len(games)} games**" in body
    assert f"lineups posted for **{posted} of {2 * len(games)}**" in body
    assert not at.error


def test_today_offline_uses_the_snapshots_date_and_does_not_let_you_change_it():
    at = start_on("today", season=2026)
    date_box = next(t for t in at.text_input if t.label == "Date")
    assert date_box.disabled and date_box.value == api.load_snapshot(2026)["schedule"]["date"]


def test_today_table_hides_started_games_until_asked_and_ranks_by_the_bats_effect():
    at = start_on("today", season=2026)
    games = api.load_snapshot(2026)["schedule"]["games"]
    not_started = sum(1 for g in games if slate.is_playable_preview(g))
    table = slate_table(at)
    assert len(table) == 2 * not_started < 2 * len(games)
    effects = table["Effect"].dropna().tolist()
    assert effects == sorted(effects, reverse=True)                      # default sort: biggest boost first
    at.checkbox(key="today_all").set_value(True).run()
    assert len(slate_table(at)) == 2 * len(games)                          # every probable starter, started or not


def test_today_uses_posted_lineups_and_says_so_per_pitcher():
    at = start_on("today", season=2026)
    at.checkbox(key="today_all").set_value(True).run()
    assert {"Posted", "Not posted yet"} <= set(slate_table(at)["Lineup"])


def test_today_matchup_watch_lists_are_ordered_and_point_the_right_way():
    at = start_on("today", season=2026)
    helped, hurt = at.dataframe[0].value, at.dataframe[1].value
    assert (helped["Effect"] > 0).all() and (hurt["Effect"] < 0).all()
    assert helped["Effect"].tolist() == sorted(helped["Effect"], reverse=True)
    assert hurt["Effect"].tolist() == sorted(hurt["Effect"])


def test_today_rejects_a_line_that_is_not_a_half_integer():
    at = start_on("today", season=2026)
    at.number_input(key="today_line").set_value(5.0).run()
    assert any("half-integer" in e.value for e in at.error)
    at.number_input(key="today_line").set_value(6.5).run()
    assert not at.error and "P(over 6.5)" in slate_table(at).columns


def test_today_offline_snapshot_without_a_slate_says_so():
    at = start_on("today", season=2025)                                      # the 2025 snapshot has no saved slate
    assert any("doesn't include a slate" in i.value for i in at.info)
    assert not at.error


def test_today_falls_back_to_team_stats_and_warns_if_batter_data_is_missing(monkeypatch):
    real = api.load_snapshot(2026)

    def without_hitters(season=None):
        snap = copy.deepcopy(real)
        del snap["hitters"]
        return snap
    monkeypatch.setattr(api, "load_snapshot", without_hitters)
    at = start_on("today", season=2026)
    assert any("Couldn't load batter stats" in w.value for w in at.warning)
    at.checkbox(key="today_all").set_value(True).run()
    assert set(slate_table(at)["Lineup"]) <= {"Not posted yet", ""}         # every game used team-level stats


def _live_with_snapshot_data(monkeypatch):
    snap = api.load_snapshot(2026)
    monkeypatch.setattr(api, "fetch_seasons", lambda: {
        "latest_completed": 2025, "options": [2026, 2025], "in_progress": [2026], "fetched_at": "test", "source": "test"})
    monkeypatch.setattr(api, "fetch_team_batting", lambda season: snap["teams"])
    monkeypatch.setattr(api, "fetch_pitchers", lambda season: snap["pitchers"])
    monkeypatch.setattr(api, "fetch_hitters", lambda season: snap["hitters"])
    return snap


def test_today_shows_a_friendly_error_when_the_schedule_cannot_be_loaded(monkeypatch):
    _live_with_snapshot_data(monkeypatch)

    def broken(day):
        raise api.ApiError("The MLB Stats API took longer than 15 seconds to answer. Try again.")
    monkeypatch.setattr(api, "fetch_schedule", broken)
    at = start_on("today", offline=False)                                    # start_on asserts there was no traceback
    assert any("Couldn't load the schedule" in e.value and "took longer" in e.value for e in at.error)


def test_today_on_an_off_day_says_there_are_no_games(monkeypatch):
    _live_with_snapshot_data(monkeypatch)
    monkeypatch.setattr(api, "fetch_schedule", lambda day: {"date": day, "games": [], "fetched_at": "test", "source": "test"})
    at = start_on("today", offline=False)
    assert any("No MLB games are scheduled" in i.value for i in at.info)


def test_today_in_live_mode_fetches_the_slate_and_game_logs_from_the_api(monkeypatch):
    snap = _live_with_snapshot_data(monkeypatch)
    monkeypatch.setattr(api, "fetch_schedule", lambda day: {**snap["schedule"], "date": day})
    monkeypatch.setattr(api, "fetch_game_log", lambda pid, season: snap["game_logs"].get(str(pid)) or {"rows": [], "fetched_at": "t", "source": "t"})
    at = start_on("today", offline=False)
    assert not at.error and "Matchup watch" in text(at)
    assert len(slate_table(at)) > 0


# ----------------------------------------------------------------- about

def test_about_page_explains_the_model_and_its_limits():
    at = start_on("about")
    assert "binomial" in text(at) and "Untested matchup formula" in text(at) and "not a betting system" in text(at)


# ---------------------------------------------------------- live failure

def test_live_mode_shows_a_friendly_error_and_offline_hint_when_the_api_is_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise requests.ConnectionError()
    monkeypatch.setattr(api.requests, "get", unreachable)
    at = start_on("home", offline=False)                  # start_on asserts there was no traceback
    assert any("Couldn't reach the MLB Stats API" in e.value for e in at.error)
    assert any("Offline demo mode" in i.value for i in at.info)
