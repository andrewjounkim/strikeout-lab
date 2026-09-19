"""slate.py -- turn one day's games into a strikeout forecast for every probable starter.

Pure logic: no network and no Streamlit, so it is easy to read and to test.

For each game there are two rows, one per starting pitcher. Each row asks the same
question the Forecast Lab asks: how many strikeouts does the model expect from THIS pitcher
against THESE opponents? There is one difference. When the opposing lineup has been posted,
the "opponent rate" comes from the nine batters in it (their pooled strikeouts / plate
appearances) instead of the whole team's season, so a lineup full of strikeout-prone hitters
raises the forecast and a lineup of contact hitters lowers it. If no lineup is posted yet, we
fall back to the team's rate and say so.

Nothing is invented: if a pitcher isn't announced, or has no starts this season, the row is
marked "not modeled" with the reason instead of getting a made-up number.
"""

import model

# A game whose lineups/pitchers are settled counts as "not started" only in this state (MLB's word).
NOT_STARTED = "Preview"


def is_playable_preview(game):
    """True for a game that hasn't started and hasn't been postponed or cancelled."""
    label = game["status"].lower()
    return game["state"] == NOT_STARTED and not label.startswith(("postponed", "cancel", "suspend"))


def analyze_slate(games, pitchers, hitters, teams, league_k, league_pa, game_logs, line):
    """Return one dict per probable pitcher.

    pitchers / hitters / teams are dicts keyed by ID (teams by team_id). game_logs maps a pitcher ID to a
    saved game log (or None). `line` is the half-integer used for the over probability.
    """
    rows = []
    for game in games:
        for side, other in (("away", "home"), ("home", "away")):
            me, opp = game[side], game[other]
            row = {
                "game_pk": game["game_pk"], "start": game["start"], "status": game["status"],
                "playable": is_playable_preview(game), "side": side,
                "pitcher_id": me["pitcher_id"], "pitcher": me["pitcher_name"] or "TBD",
                "team": me["team_name"], "opponent": opp["team_name"], "opponent_id": opp["team_id"],
                "modeled": False, "reason": None, "notes": [],
            }
            rows.append(row)

            pitcher = pitchers.get(me["pitcher_id"]) if me["pitcher_id"] is not None else None
            team = teams.get(opp["team_id"])
            if me["pitcher_id"] is None:
                row["reason"] = "Probable pitcher not announced yet"
            elif pitcher is None:
                row["reason"] = "No starts yet this season, so there's no strikeout rate to model"
            elif team is None:
                row["reason"] = "No batting data for the opponent"
            else:
                _fill_forecast(row, pitcher, opp, team, hitters, league_k, league_pa, game_logs, line)
    return rows


def _fill_forecast(row, pitcher, opp, team, hitters, league_k, league_pa, game_logs, line):
    team_rate = team["strikeouts"] / team["plate_appearances"]

    # Opponent strikeout rate: from the posted lineup if we can, otherwise the whole team.
    summary, batters = None, []
    if opp["lineup"]:
        looked_up = [hitters.get(b["id"]) for b in opp["lineup"]]
        summary = model.summarize_lineup(looked_up)
        batters = [
            {"name": b["name"], "strikeouts": h["strikeouts"], "plate_appearances": h["plate_appearances"],
             "k_rate": h["strikeouts"] / h["plate_appearances"], "low_sample": h["plate_appearances"] < model.LOW_PA}
            if h and h["plate_appearances"] else
            {"name": b["name"], "strikeouts": None, "plate_appearances": None, "k_rate": None, "low_sample": True}
            for b, h in zip(opp["lineup"], looked_up)
        ]
    if summary:
        opp_k, opp_pa, basis = summary.strikeouts, summary.plate_appearances, "lineup"
        if summary.n_batters < len(opp["lineup"]):
            row["notes"].append(f"{len(opp['lineup']) - summary.n_batters} lineup batter(s) have no stats this season yet")
        if summary.n_low_sample:
            row["notes"].append(f"{summary.n_low_sample} lineup batter(s) have under {model.LOW_PA} plate appearances")
    else:
        opp_k, opp_pa, basis = team["strikeouts"], team["plate_appearances"], "team"
        if opp["lineup"]:
            row["notes"].append("Posted lineup had too few batters with stats, so team stats were used")

    # Workload: average of the last five starts if we have a game log, else the labeled manual fallback.
    log = game_logs.get(pitcher["id"])
    suggestion = model.suggest_workload(log["rows"]) if log else None
    if suggestion:
        n, starts_used = suggestion
        workload_source = "api"
        if starts_used < 5:
            row["notes"].append(f"Workload based on only {starts_used} start(s)")
    else:
        n, starts_used, workload_source = model.MANUAL_WORKLOAD, 0, "manual"
        row["notes"].append(f"Workload is a manual assumption of {model.MANUAL_WORKLOAD} batters, not from the API")
    n = min(max(n, model.WORKLOAD_MIN), model.WORKLOAD_MAX)

    if model.is_small_sample(pitcher["batters_faced"]):
        row["notes"].append(f"Small sample: only {pitcher['batters_faced']} batters faced this season")

    try:
        forecast = model.build_forecast(
            pitcher["strikeouts"], pitcher["batters_faced"], opp_k, opp_pa, league_k, league_pa, n, line
        )
    except model.ModelInputError as error:
        row["reason"] = str(error)
        return
    if forecast.matchup.clipped:
        row["notes"].append("Matchup probability was clamped to the model's allowed range")

    row.update(
        modeled=True, forecast=forecast, basis=basis, lineup=batters or None,
        lineup_rate=summary.rate if summary else None, team_rate=team_rate,
        workload=n, workload_source=workload_source, starts_used=starts_used, pitcher_stats=pitcher,
    )


def matchup_watch(rows, top=5):
    """Split modeled, not-yet-started pitchers into 'bats help' and 'bats hurt' lists.

    Ranked by how much the opponent moves the forecast versus that pitcher's own season average
    (forecast.adjustment_effect, in strikeouts). Only rows with a real effect in that direction appear.
    """
    live = [r for r in rows if r["modeled"] and r["playable"]]
    helped = sorted((r for r in live if r["forecast"].adjustment_effect > 0),
                    key=lambda r: -r["forecast"].adjustment_effect)[:top]
    hurt = sorted((r for r in live if r["forecast"].adjustment_effect < 0),
                  key=lambda r: r["forecast"].adjustment_effect)[:top]
    return helped, hurt
