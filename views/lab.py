"""views/lab.py -- the Forecast Lab: pick a matchup, adjust it, read the forecast.

Nothing is preselected. Results appear only after you choose a pitcher AND an
opponent, so you never start out looking at a matchup you didn't ask for.
"""

import streamlit as st

import charts
import model
import state
import ui
from views.about import ASSUMPTIONS_MD

MANUAL_WORKLOAD = model.MANUAL_WORKLOAD   # used ONLY when game logs can't supply a suggestion (and labeled as manual)


def render(ctx, pages):
    ui.page_header("Forecast Lab", "Choose a pitcher and an opponent, then adjust the workload and the line.")

    pitcher, opponent_name = _pick_matchup(ctx)
    if pitcher is None:
        _empty_state(ctx, pages)
        return
    if opponent_name is None:
        st.info("**Next:** choose an opponent above to see the forecast.")
        st.page_link(pages["browse"], label="Or browse teams by strikeout rate", icon=":material/search:")
        return

    n, line, workload = _adjust(ctx, pitcher)
    _results(ctx, pitcher, opponent_name, n, line, workload)


# --------------------------------------------------------------- inputs

def _pick_matchup(ctx):
    """Steps 1 and 2. Returns (pitcher dict or None, opponent name or None)."""
    labels = {p["id"]: f"{p['name']} ({p['games_started']} starts)" for p in ctx.starters}
    pitcher_options = [None] + [p["id"] for p in ctx.starters]
    opponent_options = [None, state.LEAGUE_AVERAGE] + [t["team_name"] for t in ctx.teams]
    if st.session_state["sel_opp"] not in opponent_options:      # e.g. a team renamed between seasons
        state.choose_opponent(None)

    state.bind("sel_pitcher", "w_pitcher")
    state.bind("sel_opp", "w_opp")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        pitcher_id = c1.selectbox(
            "1 · Pitcher", pitcher_options, key="w_pitcher", on_change=state.sync, args=("sel_pitcher", "w_pitcher"),
            format_func=lambda pid: "Search or choose a pitcher..." if pid is None else labels[pid],
            placeholder="Type a name or pick from the list",
            help="Type to search. Only pitchers with at least one start in the selected season are listed.",
        )
        opponent_name = c2.selectbox(
            "2 · Opponent", opponent_options, key="w_opp", on_change=state.sync, args=("sel_opp", "w_opp"),
            format_func=lambda name: "Search or choose a team..." if name is None else name,
            placeholder="Pick the team the pitcher will face",
            help="Team-level batting statistics for the whole season. This is NOT the confirmed lineup.",
        )
        if pitcher_id is not None or opponent_name is not None:
            if st.button("Clear selection", type="tertiary"):
                state.clear_selection()
                st.rerun()
    return (ctx.pitcher(pitcher_id) if pitcher_id is not None else None), opponent_name


def _empty_state(ctx, pages):
    """What people see before they've picked anything: clear next steps, no surprise matchup."""
    with st.container(border=True):
        st.markdown("#### Start by choosing a pitcher")
        st.write(
            "Use the **Pitcher** box above (you can type a name), or browse the season's starters to see who "
            "strikes out the most. Then choose an opponent, set the workload, and the forecast appears here."
        )
        left, right = st.columns([1, 2])
        if left.button("Browse pitchers", icon=":material/search:", type="primary"):
            st.switch_page(pages["browse"])
        top = max(ctx.starters, key=lambda p: p["strikeouts"])
        team = max(ctx.teams, key=lambda t: t["k_rate"])
        if right.button(f"Just show me an example: {top['name']} vs. {team['team_name']}"):
            state.choose_pitcher(top["id"])
            state.choose_opponent(team["team_name"])
            st.rerun()
        right.caption(f"The example pairs the season's strikeout leader with the team that strikes out most often in {ctx.season}.")


def _adjust(ctx, pitcher):
    """Steps 3 and 4: workload and line. Returns (n, line, workload_info)."""
    game_log, game_log_error = ctx.game_log(pitcher["id"])
    suggestion = model.suggest_workload(game_log["rows"]) if game_log else None
    if suggestion:
        default_n, starts_used = suggestion
    else:
        default_n, starts_used = MANUAL_WORKLOAD, 0
    default_n = min(max(default_n, charts.WORKLOAD_MIN), charts.WORKLOAD_MAX)

    # One slider per pitcher (and season/mode), remembered, so switching pitchers gives that pitcher's default.
    workload_key = f"w_bf_{ctx.season}_{pitcher['id']}_{ctx.offline}"
    if workload_key not in st.session_state:
        st.session_state[workload_key] = st.session_state["bf_choice"].get(workload_key, default_n)
    state.bind("sel_line", "w_line")

    with st.container(border=True):
        c3, c4 = st.columns([3, 1])
        n = c3.slider(
            "3 · Expected batters faced", charts.WORKLOAD_MIN, charts.WORKLOAD_MAX, key=workload_key,
            on_change=state.remember_workload, args=(workload_key,),
            help="A typical start is about 22-27 batters faced (roughly 5-7 innings).",
        )
        line = c4.number_input(
            "4 · Strikeout line", min_value=0.5, max_value=15.5, step=1.0, format="%.1f", key="w_line",
            on_change=state.sync, args=("sel_line", "w_line"),
            help="A hypothetical line. Half-integers only (3.5, 4.5, 5.5 ...) so there are no ties. "
                 "For 5.5, 'over' means 6 or more.",
        )
        if suggestion:
            recent = [s["batters_faced"] for s in game_log["rows"][-5:]]
            st.caption(
                f"Suggested workload: **{default_n} batters faced**, the average of the pitcher's last {starts_used} "
                f"start{'s' if starts_used != 1 else ''} in {ctx.season} ({', '.join(map(str, recent))})"
                + (f", only {starts_used}, a small sample." if starts_used < 5 else ".")
                + (f" You've set it to **{n}**." if n != default_n else "")
            )
        else:
            why = ("no game log is saved for this pitcher in offline mode" if ctx.offline and not game_log_error
                   else game_log_error or "no recent starts were available")
            st.caption(
                f"Workload: **{n} batters faced**. The starting value of {MANUAL_WORKLOAD} is a **manual assumption, "
                f"not derived from the API** ({why})."
            )
    return n, line, {"log": game_log, "suggested": suggestion is not None, "default": default_n, "used": starts_used}


# -------------------------------------------------------------- results

def _results(ctx, pitcher, opponent_name, n, line, workload):
    try:
        line = model.validate_line(line)
        if opponent_name == state.LEAGUE_AVERAGE:
            opp_k, opp_pa = ctx.league_k, ctx.league_pa
        else:
            team = ctx.team(opponent_name)
            opp_k, opp_pa = team["strikeouts"], team["plate_appearances"]
        fc = model.build_forecast(
            pitcher["strikeouts"], pitcher["batters_faced"], opp_k, opp_pa, ctx.league_k, ctx.league_pa, n, line
        )
    except model.ModelInputError as error:
        st.error(str(error))
        return

    m = fc.matchup
    threshold = model.min_strikeouts_to_go_over(line)
    opponent_text = "a league-average offense" if opponent_name == state.LEAGUE_AVERAGE else opponent_name

    st.markdown(f"### {pitcher['name']} vs. {opponent_text}")
    st.markdown(
        f'<div class="verdict">Over <b>{n}</b> batters faced, the model expects about <b>{fc.expected:.1f} strikeouts</b>. '
        f'It gives a <b>{fc.p_over:.1%}</b> chance of {threshold} or more (over {line:.1f}) and '
        f'<b>{fc.p_under:.1%}</b> of {threshold - 1} or fewer (under {line:.1f}).</div>',
        unsafe_allow_html=True,
    )

    if model.is_small_sample(pitcher["batters_faced"]):
        st.warning(
            f"**Small sample:** this pitcher faced only {pitcher['batters_faced']} batters in {ctx.season} "
            f"(fewer than {model.SMALL_SAMPLE_BATTERS_FACED}). Their strikeout rate is very noisy "
            f"(about +/-{model.rate_standard_error(m.pitcher_rate, pitcher['batters_faced']):.1%}), so treat the forecast with extra caution."
        )
    if m.clipped:
        st.warning(
            f"**Probability clamped:** the matchup formula gave {m.p_raw:.1%} per batter, outside the model's "
            f"allowed range of {model.RATE_MIN:.0%}-{model.RATE_MAX:.0%} (an assumption), so it used {m.p:.1%}."
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Expected strikeouts", f"{fc.expected:.2f}",
        delta=f"{fc.adjustment_effect:+.2f} vs. pitcher-only ({fc.baseline_expected:.2f})", delta_color="off",
        help="Batters faced x per-batter strikeout probability. The delta is the effect of the opponent adjustment.",
    )
    c2.metric(f"Over {line:.1f}", f"{fc.p_over:.1%}", help=f"Probability of {threshold} or more strikeouts.")
    c3.metric(f"Under {line:.1f}", f"{fc.p_under:.1%}", help=f"Probability of {threshold - 1} or fewer strikeouts.")
    c4.metric(
        "Central 80% interval", f"{fc.interval_low}-{fc.interval_high} K",
        help=f"10th to 90th percentile of the model's distribution. Because strikeouts are whole numbers, it actually "
             f"covers {fc.interval_coverage:.1%}. This is a range of the MODEL's outcomes, not a guarantee.",
    )

    left, right = st.columns(2)
    left.plotly_chart(charts.probability_chart(fc), width="stretch")
    right.plotly_chart(charts.sensitivity_chart(fc), width="stretch")
    right.caption(
        "This chart shows what the model says under *alternative workload assumptions*, holding the matchup "
        "probability fixed. It is not a confidence interval."
    )

    _explanation(ctx, pitcher, opponent_name, opp_k, opp_pa, fc, workload)


def _explanation(ctx, pitcher, opponent_name, opp_k, opp_pa, fc, workload):
    m, n, line = fc.matchup, fc.n, fc.line
    threshold = model.min_strikeouts_to_go_over(line)
    is_league = opponent_name == state.LEAGUE_AVERAGE
    with st.expander("How this model works"):
        st.markdown("**1. Raw counts from the MLB Stats API**")
        st.table({
            "Source": [f"{pitcher['name']} (pitching)",
                       "League average opponent (same as league total)" if is_league else f"{opponent_name} (batting)",
                       "All MLB teams (batting, summed)"],
            "Strikeouts": [f"{pitcher['strikeouts']:,}", f"{opp_k:,}", f"{ctx.league_k:,}"],
            "Batters faced / plate appearances": [f"{pitcher['batters_faced']:,}", f"{opp_pa:,}", f"{ctx.league_pa:,}"],
        })
        st.markdown(
            "The league total is the **sum of all 30 teams' raw counts** (not an average of their percentages), "
            "so teams with more plate appearances count for more."
        )

        st.markdown("**2. Three strikeout rates, and the matchup calculation**")
        st.code(
            f"pitcher_rate  = {pitcher['strikeouts']:,} / {pitcher['batters_faced']:,}  = {m.pitcher_rate:.4f}\n"
            f"opponent_rate = {opp_k:,} / {opp_pa:,} = {m.opponent_rate:.4f}\n"
            f"league_rate   = {ctx.league_k:,} / {ctx.league_pa:,} = {m.league_rate:.4f}\n"
            f"\n"
            f"p_raw = pitcher_rate * (opponent_rate / league_rate)\n"
            f"      = {m.pitcher_rate:.4f} * ({m.opponent_rate:.4f} / {m.league_rate:.4f}) = {m.p_raw:.4f}\n"
            f"p     = clamp(p_raw, {model.RATE_MIN}, {model.RATE_MAX}) = {m.p:.4f}"
            + ("   <-- clamped" if m.clipped else ""),
            language="text",
        )
        st.markdown(
            f"Then **K ~ Binomial(N = {n}, p = {m.p:.4f})**, so the expected strikeouts are N x p = "
            f"{n} x {m.p:.4f} = **{fc.expected:.2f}**. "
            f"The probability of *over {line:.1f}* is the chance of {threshold} or more strikeouts."
        )

        st.markdown("**3. Pitcher-only baseline**")
        st.markdown(
            f"Ignoring the opponent, the expected strikeouts would be N x pitcher_rate = {n} x {m.pitcher_rate:.4f} = "
            f"**{fc.baseline_expected:.2f}**. The opponent adjustment changes that by **{fc.adjustment_effect:+.2f}** strikeouts."
        )

        game_log = workload["log"]
        if workload["suggested"]:
            st.markdown("**4. Recent starts used for the workload suggestion**")
            st.dataframe(
                [{"Date": s["date"], "Opponent": s["opponent"], "Batters faced": s["batters_faced"], "Strikeouts": s["strikeouts"]}
                 for s in reversed(game_log["rows"][-5:])],
                hide_index=True, width="stretch",
            )

        st.markdown("**Data season and fetch time**")
        datasets = list(ctx.datasets) + ([("Pitcher game log", game_log)] if game_log else [])
        st.markdown(
            f"Season used for every statistic: **{ctx.season}**"
            + (" (in progress)" if ctx.season in ctx.in_progress else " (completed)")
            + (" -- **saved offline snapshot**, not fetched now" if ctx.offline else "")
            + "\n\n" + "\n".join(f"- {label}: fetched {d['fetched_at']} -- `{d['source']}`" for label, d in datasets)
        )
        st.markdown("**Assumptions and limitations**")
        st.markdown(ASSUMPTIONS_MD)
