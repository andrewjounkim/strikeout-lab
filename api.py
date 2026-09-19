"""api.py -- talks to the public MLB Stats API (no key or login needed).

Base URL: https://statsapi.mlb.com/api/v1

Endpoints used (all verified with real requests; see API_NOTES.md):
  GET /seasons/all?sportId=1
        -> list of seasons with their start/end dates
  GET /teams/stats?stats=season&group=hitting&season=YYYY&sportIds=1
        -> one row per MLB team: batting strikeOuts and plateAppearances
  GET /stats?stats=season&group=pitching&season=YYYY&playerPool=All&sportIds=1&limit=2000
        -> one row per pitcher: strikeOuts, battersFaced, gamesStarted
  GET /people/{id}/stats?stats=gameLog&group=pitching&season=YYYY
        -> one row per game a pitcher appeared in (used to find recent starts)
  GET /schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,lineups
        -> that day's games, each side's probable starting pitcher, and posted lineups
  GET /stats?stats=season&group=hitting&season=YYYY&playerPool=All&sportIds=1&limit=2000
        -> one row per batter: strikeOuts and plateAppearances (used to rate a lineup)

Each function returns plain Python dicts/lists. The `fetch_*` functions make a
network request; the `parse_*` functions only reshape JSON, so they can be
tested without internet.

If something is missing or looks wrong, we raise ApiError with a clear message.
We never fill in made-up statistics.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://statsapi.mlb.com/api/v1"
TIMEOUT_SECONDS = 15
SNAPSHOT_DIR = Path(__file__).parent / "data"   # holds offline_snapshot_<season>.json files


class ApiError(Exception):
    """Something went wrong getting data. The message is safe to show to the user."""


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _get_json(path, params):
    """Make one GET request and return (parsed_json, final_url).

    Every failure turns into an ApiError so the app can show a friendly message.
    """
    try:
        response = requests.get(BASE_URL + path, params=params, timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        raise ApiError(f"The MLB Stats API took longer than {TIMEOUT_SECONDS} seconds to answer. Try again.") from None
    except requests.ConnectionError:
        raise ApiError("Couldn't reach the MLB Stats API. Check your internet connection.") from None
    except requests.RequestException as error:
        raise ApiError(f"The request to the MLB Stats API failed: {error}") from None

    if response.status_code == 400:
        # The API explains 400s in JSON, e.g. {"message": "Invalid season parameter: abc"}
        try:
            detail = response.json().get("message", "bad request")
        except ValueError:
            detail = "bad request"
        raise ApiError(f"The MLB Stats API rejected the request: {detail}.")
    if not response.ok:
        raise ApiError(f"The MLB Stats API returned an error (HTTP {response.status_code}). Try again later.")
    try:
        return response.json(), response.url
    except ValueError:
        raise ApiError("The MLB Stats API sent back something that wasn't valid JSON.") from None


def _first_splits(payload):
    """The stats endpoints nest rows at payload["stats"][0]["splits"]. Empty if absent."""
    blocks = payload.get("stats") or []
    return (blocks[0].get("splits") or []) if blocks else []


# ------------------------------------------------------------------ seasons

def parse_seasons(payload, today):
    """Work out which seasons exist and which is the latest COMPLETED one.

    "Completed" means the regular season's end date is before `today` (an ISO
    date string like "2026-09-19"). ISO dates sort correctly as plain text.
    """
    rows = []
    for s in payload.get("seasons") or []:
        try:
            rows.append({
                "season": int(s["seasonId"]),
                "start": s.get("regularSeasonStartDate"),
                "end": s.get("regularSeasonEndDate"),
            })
        except (KeyError, ValueError):
            continue
    completed = [r["season"] for r in rows if r["end"] and r["end"] < today]
    if not completed:
        raise ApiError("Couldn't determine the latest completed MLB season from the API.")
    latest = max(completed)
    # Offer the last 10 completed seasons, plus the current one if it has started.
    options = [
        r["season"] for r in rows
        if latest - 9 <= r["season"] and (r["end"] and r["end"] < today or r["start"] and r["start"] <= today)
    ]
    return {
        "latest_completed": latest,
        "options": sorted(set(options), reverse=True),
        "in_progress": sorted(r["season"] for r in rows
                              if r["start"] and r["start"] <= today and not (r["end"] and r["end"] < today)),
    }


def fetch_seasons(today=None):
    today = today or date.today().isoformat()
    payload, url = _get_json("/seasons/all", {"sportId": 1})
    result = parse_seasons(payload, today)
    result.update(fetched_at=_now_utc(), source=url)
    return result


# ------------------------------------------------------------- team batting

def parse_team_batting(payload, season):
    """One dict per team: batting strikeouts and plate appearances."""
    splits = _first_splits(payload)
    if not splits:
        raise ApiError(f"The API has no team batting data for {season}.")
    rows, seen = [], set()
    for s in splits:
        team = s.get("team") or {}
        stat = s.get("stat") or {}
        name = team.get("name", "an unknown team")
        if stat.get("strikeOuts") is None or not stat.get("plateAppearances"):
            # Skipping a team would quietly bias the league average, so stop instead.
            raise ApiError(f"The API is missing strikeout/plate-appearance data for {name} in {season}.")
        if team.get("id") in seen:
            raise ApiError(f"The API returned {name} twice; refusing to double-count it.")
        seen.add(team.get("id"))
        rows.append({
            "team_id": team.get("id"),
            "team_name": name,
            "strikeouts": stat["strikeOuts"],
            "plate_appearances": stat["plateAppearances"],
        })
    return sorted(rows, key=lambda r: r["team_name"])


def fetch_team_batting(season):
    payload, url = _get_json("/teams/stats", {
        "stats": "season", "group": "hitting", "season": season, "sportIds": 1,
    })
    return {"rows": parse_team_batting(payload, season), "fetched_at": _now_utc(), "source": url}


# ----------------------------------------------------------------- pitchers

def parse_pitchers(payload, season):
    """One dict per pitcher who has strikeout and batters-faced numbers.

    IMPORTANT: for a pitcher who played for several teams this endpoint already
    returns ONE row with the combined season totals (verified: a pitcher's two
    team lines add up to that row). So we never add rows together. The row's
    "team" field is only the latest team, which is why we don't use it.
    """
    splits = _first_splits(payload)
    if not splits:
        raise ApiError(f"The API has no pitcher data for {season}.")
    rows, seen = [], set()
    for s in splits:
        player = s.get("player") or {}
        stat = s.get("stat") or {}
        pid = player.get("id")
        if pid is None or stat.get("strikeOuts") is None or not stat.get("battersFaced"):
            continue  # can't model a pitcher without these two numbers
        if pid in seen:
            raise ApiError(f"The API returned {player.get('fullName')} twice; refusing to guess which row to use.")
        seen.add(pid)
        rows.append({
            "id": pid,
            "name": player.get("fullName", f"Player {pid}"),
            "strikeouts": stat["strikeOuts"],
            "batters_faced": stat["battersFaced"],
            "games_started": stat.get("gamesStarted", 0),
            "games_pitched": stat.get("gamesPlayed", 0),
        })
    return rows


def fetch_pitchers(season):
    payload, url = _get_json("/stats", {
        "stats": "season", "group": "pitching", "season": season,
        "playerPool": "All", "sportIds": 1, "limit": 2000,
    })
    return {"rows": parse_pitchers(payload, season), "fetched_at": _now_utc(), "source": url}


# ---------------------------------------------------------------- game logs

def parse_game_log(payload):
    """The pitcher's regular-season STARTS, oldest first.

    A relief appearance has gamesStarted == 0, so filtering on gamesStarted == 1
    keeps only real starts. An empty list is a valid answer (a reliever).
    """
    starts = []
    for s in _first_splits(payload):
        stat = s.get("stat") or {}
        if stat.get("gamesStarted") != 1 or s.get("gameType", "R") != "R":
            continue
        if stat.get("battersFaced") is None:
            continue
        starts.append({
            "date": s.get("date"),
            "opponent": (s.get("opponent") or {}).get("name", "?"),
            "batters_faced": stat["battersFaced"],
            "strikeouts": stat.get("strikeOuts"),
        })
    return sorted(starts, key=lambda r: r["date"] or "")


def fetch_game_log(pitcher_id, season):
    payload, url = _get_json(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog", "group": "pitching", "season": season,
    })
    return {"rows": parse_game_log(payload), "fetched_at": _now_utc(), "source": url}


# ----------------------------------------------------------------- schedule

def parse_schedule(payload):
    """That day's games, each with both sides' probable pitcher and posted lineup (if any).

    Verified quirks this handles: a side's lineup can be posted while the other side's isn't yet,
    a probable pitcher can be missing ("TBD"), and games can already be in progress or final.
    An empty list is a valid answer (an off day), not an error.
    """
    games = []
    for day in payload.get("dates") or []:
        for g in day.get("games") or []:
            teams = g.get("teams") or {}
            sides = {}
            for side in ("away", "home"):
                entry = teams.get(side) or {}
                team = entry.get("team") or {}
                pitcher = entry.get("probablePitcher") or {}
                lineup = [{"id": p["id"], "name": p.get("fullName", "?")}
                          for p in ((g.get("lineups") or {}).get(f"{side}Players") or []) if p.get("id") is not None]
                sides[side] = {
                    "team_id": team.get("id"), "team_name": team.get("name", "?"),
                    "pitcher_id": pitcher.get("id"), "pitcher_name": pitcher.get("fullName"),
                    "lineup": lineup or None,
                }
            if g.get("gamePk") is None or None in (sides["away"]["team_id"], sides["home"]["team_id"]):
                continue
            status = g.get("status") or {}
            games.append({
                "game_pk": g["gamePk"], "start": g.get("gameDate"),
                "status": status.get("detailedState", "?"), "state": status.get("abstractGameState", "?"),
                "away": sides["away"], "home": sides["home"],
            })
    return sorted(games, key=lambda x: (x["start"] or "", x["game_pk"]))


def fetch_schedule(day):
    """`day` is an ISO date string like "2026-09-19"."""
    payload, url = _get_json("/schedule", {"sportId": 1, "date": day, "hydrate": "probablePitcher,lineups"})
    return {"date": day, "games": parse_schedule(payload), "fetched_at": _now_utc(), "source": url}


# ------------------------------------------------------------------ hitters

def parse_hitters(payload, season):
    """One dict per batter who has batted: strikeouts and plate appearances.

    Batters with no plate appearances (mostly pitchers) are skipped. As with pitchers, a
    batter who changed teams already has ONE combined row (verified: Luis Arraez's two
    team lines add up to his single row), so rows are never added together.
    """
    splits = _first_splits(payload)
    if not splits:
        raise ApiError(f"The API has no hitter data for {season}.")
    rows, seen = [], set()
    for s in splits:
        player = s.get("player") or {}
        stat = s.get("stat") or {}
        pid = player.get("id")
        if pid is None or stat.get("strikeOuts") is None or not stat.get("plateAppearances"):
            continue
        if pid in seen:
            raise ApiError(f"The API returned {player.get('fullName')} twice; refusing to guess which row to use.")
        seen.add(pid)
        rows.append({"id": pid, "name": player.get("fullName", f"Player {pid}"),
                     "strikeouts": stat["strikeOuts"], "plate_appearances": stat["plateAppearances"]})
    return rows


def fetch_hitters(season):
    payload, url = _get_json("/stats", {
        "stats": "season", "group": "hitting", "season": season,
        "playerPool": "All", "sportIds": 1, "limit": 2000,
    })
    return {"rows": parse_hitters(payload, season), "fetched_at": _now_utc(), "source": url}


# ------------------------------------------------------------ offline demo

def snapshot_path(season):
    return SNAPSHOT_DIR / f"offline_snapshot_{season}.json"


def available_snapshot_seasons():
    """The seasons that have a saved offline snapshot, newest first."""
    seasons = []
    for path in SNAPSHOT_DIR.glob("offline_snapshot_*.json"):
        suffix = path.stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            seasons.append(int(suffix))
    return sorted(seasons, reverse=True)


def load_snapshot(season=None):
    """Read a saved real-API snapshot for Offline demo mode (the newest one if no season is given)."""
    if season is None:
        seasons = available_snapshot_seasons()
        if not seasons:
            raise ApiError("No offline snapshot is saved. Run make_snapshot.py to create one.")
        season = seasons[0]
    try:
        with open(snapshot_path(season), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise ApiError(f"The offline snapshot for {season} is missing or unreadable. "
                       "Run make_snapshot.py to create it.") from None
