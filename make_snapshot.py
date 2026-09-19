"""make_snapshot.py -- save a small REAL copy of the API data for Offline demo mode.

Run (needs internet):   python make_snapshot.py 2026     (or 2025, or any season)

It calls the same fetch functions the app uses and writes data/offline_snapshot_<season>.json.
Every section keeps the exact API URL it came from and the time it was fetched,
so the app can label offline data honestly. Nothing here is invented.

Size is kept small: every pitcher with at least one start, every batter with a plate
appearance, that day's slate, and game logs for only a handful of pitchers (the top
strikeout starters, a few small-sample starters so the small-sample warning can be
demonstrated offline, and that day's probable starters).
Pitchers without a saved game log fall back to the manual 24-batter default,
and the app says so.
"""

import json
import sys
from datetime import date

import api

TOP_STARTERS = 20   # by strikeouts, among pitchers with 20+ starts
SMALL_SAMPLES = 3   # pitchers with only 1-2 starts


def main(season):
    teams = api.fetch_team_batting(season)
    pitchers = api.fetch_pitchers(season)
    starters = [p for p in pitchers["rows"] if p["games_started"] >= 1]

    workhorses = sorted((p for p in starters if p["games_started"] >= 20), key=lambda p: -p["strikeouts"])
    small = sorted((p for p in starters if p["games_started"] <= 2), key=lambda p: p["name"])
    chosen = workhorses[:TOP_STARTERS] + small[:SMALL_SAMPLES]

    game_logs = {}
    for p in chosen:
        print("fetching game log:", p["name"])
        game_logs[str(p["id"])] = api.fetch_game_log(p["id"], season)

    # Also save the day's slate (games, probable pitchers, posted lineups) and every batter's season
    # totals, so the "Today" page works offline. Its date is the day the snapshot was made.
    hitters = api.fetch_hitters(season)
    schedule = api.fetch_schedule(date.today().isoformat())
    starter_ids = {p["id"] for p in starters}
    for game in schedule["games"]:
        for side in ("away", "home"):
            pid = game[side]["pitcher_id"]
            if pid in starter_ids and str(pid) not in game_logs:
                print("fetching game log (probable pitcher):", game[side]["pitcher_name"])
                game_logs[str(pid)] = api.fetch_game_log(pid, season)

    snapshot = {
        "season": season,
        "in_progress": season in api.fetch_seasons()["in_progress"],   # partial-season data changes daily
        "created_at": teams["fetched_at"],
        "note": ("A saved extract of real MLB Stats API responses, for offline demo use only. "
                 "Pitchers are limited to those with at least one start."),
        "teams": teams,
        "hitters": hitters,
        "schedule": schedule,
        "pitchers": {**pitchers, "rows": starters},
        "game_logs": game_logs,
    }
    path = api.snapshot_path(season)
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, separators=(",", ":"))
    print(f"saved {path} ({path.stat().st_size / 1024:.0f} KB): "
          f"{len(starters)} pitchers, {len(game_logs)} game logs")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2025)
