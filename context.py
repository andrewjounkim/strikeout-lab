"""context.py -- loads the data every page needs and draws the shared sidebar.

`setup()` runs on every page load, BEFORE the page itself. It shows the "Data"
controls (season, offline mode), loads that season's statistics (from the cache
after the first time), and returns a Context the pages can read from.

The cached loaders are the only place besides api.py that touches the network.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import streamlit as st

import api
import model
import state

CACHE_SECONDS = 6 * 60 * 60   # reuse fetched data for 6 hours
OFFLINE_HINT = "You can still explore the app: tick **Offline demo mode** in the sidebar to use saved data."


# Each loader returns data or raises api.ApiError. Errors are NOT cached, so trying
# again after a network hiccup really does try again.

@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading seasons from the MLB Stats API...")
def load_seasons():
    return api.fetch_seasons()


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading team and pitcher stats from the MLB Stats API...")
def load_season_data(season):
    return {"teams": api.fetch_team_batting(season), "pitchers": api.fetch_pitchers(season)}


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading recent starts from the MLB Stats API...")
def load_game_log(pitcher_id, season):
    return api.fetch_game_log(pitcher_id, season)


@st.cache_data(ttl=5 * 60, show_spinner="Loading the day's games from the MLB Stats API...")
def load_schedule(day):
    return api.fetch_schedule(day)      # short cache: lineups get posted throughout the day


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading batter stats from the MLB Stats API...")
def load_hitters(season):
    return api.fetch_hitters(season)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading recent starts for today's pitchers...")
def load_game_logs(pitcher_ids, season):
    """Fetch several pitchers' game logs at once (in parallel, so a full slate isn't slow).

    Returns {pitcher_id: game_log or None}; None means that one request failed (the page then falls
    back to the labeled manual workload for that pitcher instead of failing everything).
    """
    def one(pid):
        try:
            return pid, api.fetch_game_log(pid, season)
        except api.ApiError:
            return pid, None
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(one, pitcher_ids))


@st.cache_data
def load_offline_snapshot(season):
    return api.load_snapshot(season)


@dataclass
class Context:
    season: int
    offline: bool
    in_progress: list
    teams: list            # one dict per team: strikeouts, plate_appearances, k_rate, vs_league
    starters: list         # one dict per pitcher with 1+ start: strikeouts, batters_faced, k_rate ...
    league_k: int
    league_pa: int
    datasets: list         # (label, {"fetched_at", "source"}) for the "data source" panel
    snapshot: dict = None  # the offline snapshot, when in offline mode

    @property
    def league_rate(self):
        return self.league_k / self.league_pa

    def pitcher(self, pitcher_id):
        return next((p for p in self.starters if p["id"] == pitcher_id), None)

    def team(self, name):
        return next((t for t in self.teams if t["team_name"] == name), None)

    def slate(self, day):
        """The saved (offline) or live schedule for a day. Returns None if offline with no saved slate."""
        if self.offline:
            return self.snapshot.get("schedule")
        return load_schedule(day)

    def hitters(self):
        """Batter stats keyed by player ID. Raises api.ApiError if unavailable."""
        if self.offline:
            if not self.snapshot.get("hitters"):
                raise api.ApiError("This offline snapshot has no batter data.")
            return {h["id"]: h for h in self.snapshot["hitters"]["rows"]}
        return {h["id"]: h for h in load_hitters(self.season)["rows"]}

    def game_logs(self, pitcher_ids):
        """{pitcher_id: game log or None} for several pitchers at once."""
        ids = tuple(sorted(set(pitcher_ids)))
        if self.offline:
            return {pid: self.snapshot["game_logs"].get(str(pid)) for pid in ids}
        return load_game_logs(ids, self.season)

    def default_workload(self, pitcher_id):
        """(batters_faced, source, starts_used, game_log): the average of the last 5 starts, else the labeled manual value."""
        log, _ = self.game_log(pitcher_id)
        suggestion = model.suggest_workload(log["rows"]) if log else None
        n, used, source = (suggestion[0], suggestion[1], "api") if suggestion else (model.MANUAL_WORKLOAD, 0, "manual")
        return min(max(n, model.WORKLOAD_MIN), model.WORKLOAD_MAX), source, used, log

    def game_log(self, pitcher_id):
        """Return (game_log_or_None, error_message_or_None) for one pitcher."""
        if self.offline:
            return self.snapshot["game_logs"].get(str(pitcher_id)), None
        try:
            return load_game_log(pitcher_id, self.season), None
        except api.ApiError as error:
            return None, str(error)


def fail(message, hint=None):
    """Show a friendly error and stop the whole page."""
    st.error(message)
    if hint:
        st.info(hint)
    st.stop()


def setup():
    """Draw the sidebar, load the data, and return a Context (or stop with a clear error)."""
    st.sidebar.markdown("### Data")
    offline = st.sidebar.checkbox(
        "Offline demo mode (saved data)", value=False, key="offline_mode",
        help="Uses a saved snapshot of real API data instead of calling the API. Handy with no internet.",
    )
    if st.sidebar.button("Refresh data from API", disabled=offline):
        st.cache_data.clear()
        st.rerun()

    snapshot, in_progress = None, []
    if offline:
        saved_seasons = api.available_snapshot_seasons()
        if not saved_seasons:
            fail("No offline snapshot is saved. Run make_snapshot.py to create one.")
        season = st.sidebar.selectbox("Season (saved snapshots)", saved_seasons, key="offline_season")
        try:
            snapshot = load_offline_snapshot(season)
        except api.ApiError as error:
            fail(str(error))
        in_progress = [season] if snapshot.get("in_progress") else []
        season_data = {"teams": snapshot["teams"], "pitchers": snapshot["pitchers"]}
        st.warning(
            f"**OFFLINE DEMO MODE:** showing saved data from the {season} season, fetched from the API on "
            f"{snapshot['created_at']}. This is not live data."
        )
    else:
        try:
            seasons = load_seasons()
        except api.ApiError as error:
            fail(f"Couldn't load the list of seasons. {error}", OFFLINE_HINT)
        in_progress = seasons["in_progress"]
        season = st.sidebar.selectbox(
            "Season (supplies all the statistics)", seasons["options"],   # newest first, so it opens on the current season
            format_func=lambda s: f"{s} (in progress)" if s in in_progress else str(s),
            help="Opens on the current season. Choose an earlier one for complete, final numbers.",
        )
        try:
            season_data = load_season_data(season)
        except api.ApiError as error:
            fail(f"Couldn't load {season} statistics. {error}", OFFLINE_HINT)

    if season in in_progress:
        st.info(f"{season} is still in progress, so these are partial-season statistics and will keep changing.")
    if season == 2020:
        st.info("2020 was a shortened 60-game season, so every pitcher's sample is much smaller than usual.")

    team_rows = season_data["teams"]["rows"]
    league_k, league_pa = model.league_totals(team_rows)
    league_rate = league_k / league_pa
    teams = []
    for t in team_rows:
        rate = t["strikeouts"] / t["plate_appearances"]
        teams.append({**t, "k_rate": rate, "vs_league": rate / league_rate - 1})
    starters = sorted(
        ({**p, "k_rate": p["strikeouts"] / p["batters_faced"]}
         for p in season_data["pitchers"]["rows"] if p["games_started"] >= 1),
        key=lambda p: p["name"],
    )
    if not starters:
        fail(f"No pitchers with a start were found for {season}.", None if offline else OFFLINE_HINT)

    if state.drop_unavailable_pitcher({p["id"] for p in starters}):
        st.toast(f"Your chosen pitcher has no starts in {season}, so the selection was cleared.")

    return Context(
        season=season, offline=offline, in_progress=in_progress, teams=teams, starters=starters,
        league_k=league_k, league_pa=league_pa, snapshot=snapshot,
        datasets=[("Team batting", season_data["teams"]), ("All pitchers", season_data["pitchers"])],
    )
