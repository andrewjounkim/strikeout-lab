"""views/today.py -- today's games: who the opposing bats could help or hurt.

For every probable starter on the slate this shows the model's expected strikeouts against the
actual opposing lineup (once it is posted; team stats until then), compared with that pitcher's
own season average. It is a forecast comparison, not betting advice: the model has no sportsbook
lines and has never been validated, so it can't say what is a "good bet".
"""

from html import escape

import pandas as pd
import streamlit as st

import api
import model
import slate
import state
import ui

SORTS = {
    "Biggest boost from the bats": lambda r: -r["forecast"].adjustment_effect,
    "Biggest drag from the bats": lambda r: r["forecast"].adjustment_effect,
    "Start time": lambda r: (r["start"] or "", r["game_pk"]),
    "Most expected strikeouts": lambda r: -r["forecast"].expected,
}

WHAT_THIS_IS = (
    "**What this page is, and isn't.** For each probable starter, it shows how many strikeouts the model expects "
    "against the actual opposing lineup (team stats until the lineup is posted), compared with that pitcher's own "
    "season average. Bats that **help** mean more strikeouts than usual; bats that **hurt** mean fewer. "
    "It can't tell you what is a good bet: it has no sportsbook lines, and its formula has never been tested "
    "against real results. Use it to see *how a lineup changes a forecast*, not as advice."
)


def render(ctx, pages):
    ui.page_header("Today's Games", "Every probable starter on the slate, and whether the opposing bats could help or hurt.")
    st.info(WHAT_THIS_IS)

    day, line, include_started = _controls(ctx)
    if day is None:
        return
    try:
        schedule = ctx.slate(day)
    except api.ApiError as error:
        st.error(f"Couldn't load the schedule. {error}")
        return
    if schedule is None:      # defensive: offline snapshots without a slate are handled in _controls
        return
    games = schedule["games"]
    if not games:
        st.info(f"No MLB games are scheduled for {day}. Try a different date.")
        return

    if int(day[:4]) != ctx.season:
        st.warning(f"This slate is from {day[:4]}, but the statistics come from the {ctx.season} season selected in the sidebar.")
    try:
        hitters = ctx.hitters()
    except api.ApiError as error:
        hitters = {}
        st.warning(f"Couldn't load batter stats ({error}), so team-level stats are used for every game.")

    pitchers = {p["id"]: p for p in ctx.starters}
    teams = {t["team_id"]: t for t in ctx.teams}
    logs = ctx.game_logs([g[s]["pitcher_id"] for g in games for s in ("away", "home") if g[s]["pitcher_id"] in pitchers])
    rows = slate.analyze_slate(games, pitchers, hitters, teams, ctx.league_k, ctx.league_pa, logs, line)
    visible = [r for r in rows if r["playable"] or include_started]

    _summary(games, rows, schedule, ctx)
    _watch(rows, line)
    _all_pitchers(ctx, pages, visible, line, include_started)


# -------------------------------------------------------------- controls

def _controls(ctx):
    """Date, line, and the started-games checkbox. Returns (iso date or None, line, include_started)."""
    c1, c2, c3 = st.columns([2, 2, 3])
    if ctx.offline:
        saved = (ctx.snapshot.get("schedule") or {}).get("date")
        c1.text_input("Date", value=saved or "no saved slate", disabled=True, help="Offline mode shows the slate saved with the snapshot.")
        if not saved:
            st.info("This saved offline snapshot doesn't include a slate. Pick the 2026 snapshot in the sidebar, "
                    "or turn off Offline demo mode to load today's games.")
            return None, state.DEFAULT_LINE, False
        day = saved
    else:
        day = c1.date_input("Date", value=api.mlb_today(), key="today_date", help="Probable pitchers are usually posted a day or two ahead.").isoformat()
    line = c2.number_input("Strikeout line", min_value=0.5, max_value=15.5, value=state.DEFAULT_LINE, step=1.0,
                           format="%.1f", key="today_line", help="Hypothetical. Half-integers only, so there are no ties.")
    include_started = c3.checkbox("Include games already started or finished", value=False, key="today_all",
                                  help="Their forecasts still use season stats, so they can't be judged against the result.")
    try:
        line = model.validate_line(line)
    except model.ModelInputError as error:
        st.error(str(error))
        return None, line, include_started
    return day, line, include_started


# --------------------------------------------------------------- summary

def _summary(games, rows, schedule, ctx):
    started = sum(1 for g in games if not slate.is_playable_preview(g))
    sides = [g[s] for g in games for s in ("away", "home")]
    posted = sum(1 for x in sides if x["lineup"])
    modeled = sum(1 for r in rows if r["modeled"])
    st.caption(
        f"**{len(games)} games** on {schedule['date']} ({len(games) - started} not started) · lineups posted for "
        f"**{posted} of {len(sides)}** teams · **{modeled} of {len(rows)}** probable starters modeled · "
        f"statistics from the {ctx.season} season · schedule fetched {schedule['fetched_at']}"
    )


# ----------------------------------------------------------- matchup watch

def _watch(rows, line):
    st.markdown("### Matchup watch")
    helped, hurt = slate.matchup_watch(rows)
    if not helped and not hurt:
        st.info("No games left to preview today: every game has started or finished, or no probable starters could be modeled.")
        return
    st.caption("Ranked by *effect*: the model's expected strikeouts minus that pitcher's own season average at the same workload. "
               "Only games that haven't started are listed.")
    # Stacked (not side by side) so all five columns fit without being clipped.
    for title, subset in (("Bats that could help", helped), ("Bats that could hurt", hurt)):
        st.markdown(f"**{title}**")
        if not subset:
            st.caption("None.")
            continue
        st.dataframe(
            pd.DataFrame({
                "Pitcher": [r["pitcher"] for r in subset],
                "vs": [r["opponent"] for r in subset],
                "Exp. K": [r["forecast"].expected for r in subset],
                "Effect": [r["forecast"].adjustment_effect for r in subset],
                "Basis": ["Lineup" if r["basis"] == "lineup" else "Team" for r in subset],
            }),
            hide_index=True, width="stretch",
            column_config={
                "Exp. K": st.column_config.NumberColumn(format="%.2f", width="small", help="Expected strikeouts."),
                "Effect": st.column_config.NumberColumn(format="%+.2f", width="small", help="Expected K minus this pitcher's own season average."),
                "Basis": st.column_config.TextColumn(width="small", help="Whether the posted lineup or the team's season stats were used."),
            },
        )


# -------------------------------------------------------- all pitchers

def _all_pitchers(ctx, pages, visible, line, include_started):
    st.markdown("### All probable starters")
    if not visible:
        st.info("No games to show. Tick 'Include games already started or finished' to see today's earlier games.")
        return
    sort_label = st.selectbox("Sort by", list(SORTS), key="today_sort")
    modeled = sorted((r for r in visible if r["modeled"]), key=SORTS[sort_label])
    unmodeled = [r for r in visible if not r["modeled"]]
    ordered = modeled + unmodeled
    over_col = f"P(over {line:.1f})"

    frame = pd.DataFrame({
        "Time (ET)": [ui.game_time(r["start"]) for r in ordered],
        "Pitcher": [r["pitcher"] for r in ordered],
        "Team": [r["team"] for r in ordered],
        "vs": [r["opponent"] for r in ordered],
        "Lineup": [("Posted" if r["basis"] == "lineup" else "Not posted yet") if r["modeled"] else "" for r in ordered],
        "Expected K": [r["forecast"].expected if r["modeled"] else None for r in ordered],
        "Own avg K": [r["forecast"].baseline_expected if r["modeled"] else None for r in ordered],
        "Effect": [r["forecast"].adjustment_effect if r["modeled"] else None for r in ordered],
        over_col: [r["forecast"].p_over * 100 if r["modeled"] else None for r in ordered],
        "80% range": [f"{r['forecast'].interval_low}-{r['forecast'].interval_high} K" if r["modeled"] else "" for r in ordered],
        "Status": [r["status"] for r in ordered],
        "Notes": [(" · ".join(r["notes"]) if r["modeled"] else r["reason"]) for r in ordered],
    })
    st.caption("Click a row to see the batters behind it. Rows the model can't handle are listed last, with the reason.")
    event = st.dataframe(
        frame, key="today_table", on_select="rerun", selection_mode="single-row", hide_index=True, width="stretch", height=430,
        column_config={
            "Expected K": st.column_config.NumberColumn(format="%.2f"),
            "Own avg K": st.column_config.NumberColumn(format="%.2f", help="What the pitcher's season average implies at this workload, ignoring the opponent."),
            "Effect": st.column_config.NumberColumn(format="%+.2f", help="Expected K minus own average."),
            over_col: st.column_config.ProgressColumn(over_col, format="%.0f%%", min_value=0, max_value=100),
        },
    )
    picked = event.selection.rows
    if not picked:
        st.info("Select a pitcher in the table above to see the opposing lineup.")
        return
    _detail(ctx, pages, ordered[picked[0]], line)


def _detail(ctx, pages, row, line):
    with st.container(border=True):
        title = f"{row['pitcher']} ({row['team']}) vs. {row['opponent']}"
        st.markdown(f"#### {escape(title)}")
        if not row["modeled"]:
            st.warning(f"Not modeled: {row['reason']}.")
            return
        fc = row["forecast"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected strikeouts", f"{fc.expected:.2f}")
        c2.metric("Own season average", f"{fc.baseline_expected:.2f}", help="At the same workload, ignoring the opponent.")
        c3.metric("Effect of the bats", f"{fc.adjustment_effect:+.2f}", help="Expected minus own average.")
        c4.metric(f"Over {line:.1f}", f"{fc.p_over:.1%}", help=f"Probability of {model.min_strikeouts_to_go_over(line)} or more strikeouts.")

        if row["basis"] == "lineup":
            diff = (row["lineup_rate"] - row["team_rate"]) * 100
            st.markdown(
                f"**Based on {row['opponent']}'s posted lineup.** Together these batters strike out "
                f"**{row['lineup_rate']:.1%}** of the time this season, versus {row['team_rate']:.1%} for the whole team "
                f"({diff:+.1f} points) and {ctx.league_rate:.1%} for the league."
            )
            _lineup_table(row["lineup"])
        else:
            st.markdown(
                f"**Based on {row['opponent']}'s team stats** ({row['team_rate']:.1%} strikeouts per plate appearance vs. "
                f"{ctx.league_rate:.1%} for the league). Their lineup hasn't been posted yet, so check back closer to first pitch."
            )
        workload = (f"{row['workload']} batters faced, the average of the pitcher's last {row['starts_used']} starts"
                    if row["workload_source"] == "api" else f"{row['workload']} batters faced (a manual assumption)")
        st.caption(f"Workload: {workload}.")
        for note in row["notes"]:
            st.caption(f"Note: {note}")

        if st.button("Open in the Forecast Lab →", key=f"today_open_{row['game_pk']}_{row['pitcher_id']}"):
            state.choose_pitcher(row["pitcher_id"])
            state.choose_opponent(next(t["team_name"] for t in ctx.teams if t["team_id"] == row["opponent_id"]))
            st.switch_page(pages["lab"])
        st.caption("The Lab uses team-level opponent stats, so its numbers can differ from the lineup-based ones here.")


def _lineup_table(batters):
    ranked = sorted((b for b in batters if b["k_rate"] is not None and not b["low_sample"]), key=lambda b: -b["k_rate"])
    top = {b["name"] for b in ranked[:3]}
    st.dataframe(
        pd.DataFrame({
            "Batter": [b["name"] for b in batters],
            "K rate": [b["k_rate"] * 100 if b["k_rate"] is not None else None for b in batters],
            "Plate appearances": [b["plate_appearances"] for b in batters],
            "Flag": ["no stats yet" if b["k_rate"] is None else ("small sample" if b["low_sample"] else ("most strikeout-prone" if b["name"] in top else ""))
                     for b in batters],
        }),
        hide_index=True, width="stretch",
        column_config={
            "K rate": st.column_config.ProgressColumn("K rate", format="%.1f%%", min_value=0, max_value=45),
            "Plate appearances": st.column_config.NumberColumn(format="%d"),
        },
    )
