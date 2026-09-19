# API notes: what I verified

Everything here comes from real requests made on 2026-09-19 to the public
**MLB Stats API** (`https://statsapi.mlb.com/api/v1`). No API key or login is
needed. The app itself re-fetches this data and shows the exact URL and fetch
time for each dataset inside its "How this model works" panel.

## Endpoints, parameters, and fields actually used

| Purpose | Request | Fields read |
|---|---|---|
| Which seasons exist / which is the latest completed | `GET /seasons/all?sportId=1` | `seasons[].seasonId`, `regularSeasonStartDate`, `regularSeasonEndDate` |
| Opponent batting + league totals | `GET /teams/stats?stats=season&group=hitting&season=YYYY&sportIds=1` | `stats[0].splits[]` → `team.id`, `team.name`, `stat.strikeOuts`, `stat.plateAppearances` |
| Pitcher season lines | `GET /stats?stats=season&group=pitching&season=YYYY&playerPool=All&sportIds=1&limit=2000` | `stats[0].splits[]` → `player.id`, `player.fullName`, `stat.strikeOuts`, `stat.battersFaced`, `stat.gamesStarted`, `stat.gamesPlayed` |
| Recent starts (workload) | `GET /people/{id}/stats?stats=gameLog&group=pitching&season=YYYY` | `stats[0].splits[]` → `date`, `gameType`, `opponent.name`, `stat.gamesStarted`, `stat.battersFaced`, `stat.strikeOuts` |
| A day's games (Today page) | `GET /schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,lineups` | `dates[].games[]` → `gamePk`, `gameDate`, `status.detailedState` / `abstractGameState`, `teams.{away,home}.team.{id,name}`, `teams.*.probablePitcher.{id,fullName}`, `lineups.{away,home}Players[].{id,fullName}` |
| Batter season lines (lineup rates) | `GET /stats?stats=season&group=hitting&season=YYYY&playerPool=All&sportIds=1&limit=2000` | `stats[0].splits[]` → `player.id`, `player.fullName`, `stat.strikeOuts`, `stat.plateAppearances` |

A `GET /teams?sportId=1&season=YYYY` call (30 teams with IDs, names, abbreviations)
also works, but the team-batting response already contains each team's ID and name,
so the app does not need it.

## What the checks showed

- **Team batting:** 30 distinct rows (one per team), each with `strikeOuts` and
  `plateAppearances`. There is no aggregate/"league" row mixed in, so summing the
  30 rows cannot double-count. 2025 league total: 40,645 strikeouts over 182,926
  plate appearances = 22.22%.
- **Pitchers:** one row per pitcher (873 in 2025; 369 with at least one start).
- **Pitchers who changed teams:** this endpoint returns **one row with the combined
  season totals**. Checked against `/people/{id}/stats`, which returns the combined
  row *plus* one row per team: Tyler Rogers' 10 K / 111 BF (Mets) + 38 K / 188 BF
  (Giants) = 48 K / 299 BF, exactly his single combined row. Two consequences:
  the app never adds pitcher rows together, and it never uses the row's `team`
  field (that is just his latest team).
  Summing `/people/{id}/stats` rows would double-count, so the app doesn't use
  that endpoint for season totals.
- **Game logs:** one row per appearance, sorted by date. `gamesStarted` is 1 for a
  start and 0 for relief, so filtering on it keeps only real starts (checked on a
  pitcher with 3 starts and 8 relief outings). For one full-time starter the log
  totals (255 K, 814 BF, 32 GS) matched his season line exactly. `gameType` was
  `R` (regular season) for every row.
- **Bad requests:** a season with no data (e.g. 2030 or 1800) returns HTTP 200 with an
  empty `stats` list, not an error; a malformed season (`season=abc`) returns HTTP 400
  with a JSON `message`; an unknown player ID returns an empty list. The app treats
  each of these as an explicit "no data" error instead of inventing numbers.
- **Seasons available in the app:** the 10 most recent completed seasons plus the
  current one if it has started. All 11 were checked (2016 through 2026): each
  returned 30 teams and 735-909 pitchers, with league strikeout rates rising
  from 21.1% (2016) to about 23% (2019-2021), as expected. "Completed" means the
  regular season's end date is before today (2025 as of 2026-09-19).
- **The default season is the current one (2026, in progress as of 2026-09-19)**, per the
  project owner's request, with the completed seasons one click away. Checked for 2026: 30 teams
  averaging about 151 games, league strikeout rate 22.1%, 859 pitchers (366 with a start), and a
  game log that reconciles exactly with the season line (243 K, 636 BF). Because 2026 is partial,
  its numbers change daily; a "still in progress" notice is shown whenever it is selected.

## What the Today-page checks showed (2026-09-19)

- **Schedule:** 15 games, each side with a probable pitcher. Game states were a real mix (`Final`,
  `Live`, `Preview`; detailed labels like `Pre-Game`, `In Progress`), so only `Preview` games are ranked.
  No doubleheaders that day, but games are keyed by `gamePk`, not by team.
- **Lineups are per side and appear gradually.** That day 25 of 30 team-sides had a posted lineup (always
  9 batters) and 5 did not; a game can have one team's lineup and not the other's. Looking at tomorrow's
  slate (2026-09-20) later showed 0 of 30 posted. A side with no lineup falls back to the team's rate.
- **Batter stats:** one row per batter (743 rows for 2026). About 84 had no plate appearances (almost all
  pitchers) and are skipped. As with pitchers, a batter who changed teams has **one combined row**: Luis
  Arraez's two team lines (28 K / 635 PA in total) equal his single row exactly, so nothing is added together.
- **Coverage:** all 225 players in the posted lineups had usable stats; 16 had under 100 plate appearances
  (flagged as small samples on the page). A lineup is used only if at least 7 of its batters have stats.
- **Unmodeled probable starters:** a starter with no starts yet that season (or no announced starter) has no
  strikeout rate to model, so the page lists them last with the reason instead of guessing.

## Other network use

Besides the endpoints above, Google Fonts was contacted **once, at design time**, to download the Inter and Barlow
Condensed font files, which are now bundled in `static/fonts/`. The running app calls only `statsapi.mlb.com`
and needs no API key, so the project holds no secrets (verified by a repo-wide scan and an automated test).

## Limitations of the data

- Innings pitched are stored in baseball notation (`"6.1"` means 6⅓), so the model
  uses **batters faced** and never treats innings as a decimal.
- Opponent numbers are team-level season totals. They cover every batter who
  appeared for that team, not the lineup that will actually play.
- Opponent strikeouts are measured against all pitchers the team faced, not just
  the selected pitcher's handedness or style.
- A lineup's season totals ignore batting order (leadoff hitters bat more), left/right platoon
  matchups, and whether a regular is hurt or resting. Probable pitchers can also change before first pitch.
- The MLB Stats API is public but not formally documented for this use, so field
  names could change in the future.
