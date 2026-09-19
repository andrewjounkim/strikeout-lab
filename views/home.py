"""views/home.py -- the landing page: a hero with the mission, live numbers, an interactive
"try it" forecast, today's slate, and strikeout leaders. Everything shown is real MLB data
(nothing decorative is made up), and each section leads somewhere.
"""

from datetime import date
from html import escape

import streamlit as st

import api
import charts
import model
import slate
import state
import ui


def render(ctx, pages):
    in_progress = ctx.season in ctx.in_progress
    ui.hero(ctx.season, ctx.offline, in_progress)

    # Three big buttons so the next step is obvious.
    left, middle, right, _ = st.columns([1, 1, 1, 1])
    if left.button("Browse pitchers", icon=":material/search:", type="primary", width="stretch"):
        st.switch_page(pages["browse"])
    if middle.button("Today's games", icon=":material/today:", width="stretch"):
        st.switch_page(pages["today"])
    if right.button("Open the Forecast Lab", icon=":material/science:", width="stretch"):
        st.switch_page(pages["lab"])

    _tiles(ctx, in_progress)
    _try_it(ctx, pages)
    _today_teaser(ctx, pages)
    _leaders(ctx, pages, in_progress)
    _how_it_works(pages)

    st.divider()
    st.caption(
        "Strikeout Lab is an educational statistics project. It is not a betting system, and it makes no "
        "claim to be accurate or to beat any sportsbook. Data: the public MLB Stats API."
    )


# ------------------------------------------------------------ live numbers

def _tiles(ctx, in_progress):
    so_far = " so far" if in_progress else ""
    top = max(ctx.starters, key=lambda p: p["strikeouts"])
    team = max(ctx.teams, key=lambda t: t["k_rate"])
    ui.tiles([
        (f"{ctx.league_rate:.1%}", f"of MLB plate appearances end in a strikeout in {ctx.season}{so_far}", False),
        (f"{ctx.league_k:,}", f"strikeouts recorded across MLB in {ctx.season}{so_far}", False),
        (top["name"], f"{top['strikeouts']} strikeouts: the season's strikeout leader", True),
        (team["team_name"], f"{team['k_rate']:.1%} strikeout rate: the most strikeout-prone offense", True),
    ])


# ------------------------------------------------------- interactive widget

def _pick(key, value):
    """Button callback: set a widget's value (runs before the page redraws)."""
    st.session_state[key] = value


def _try_it(ctx, pages):
    ui.eyebrow("Interactive")
    st.markdown("### Try it: build a matchup in two clicks")
    st.caption("Pick a pitcher and the team they'll face, and the forecast appears instantly. Nothing is preselected.")

    ids = [p["id"] for p in ctx.starters]
    teams = [t["team_name"] for t in ctx.teams]
    pitcher_options, opponent_options = [None] + ids, [None, state.LEAGUE_AVERAGE] + teams
    if st.session_state.get("home_pitcher") not in pitcher_options:      # e.g. after switching seasons
        st.session_state.pop("home_pitcher", None)
    if st.session_state.get("home_opp") not in opponent_options:
        st.session_state.pop("home_opp", None)

    with st.container(border=True):
        top3 = sorted(ctx.starters, key=lambda p: -p["strikeouts"])[:3]
        heavy = max(ctx.teams, key=lambda t: t["k_rate"])
        light = min(ctx.teams, key=lambda t: t["k_rate"])
        st.caption("Quick picks")
        cols = st.columns(5)
        for column, p in zip(cols[:3], top3):
            column.button(p["name"], key=f"qp_{p['id']}", on_click=_pick, args=("home_pitcher", p["id"]), width="stretch")
        cols[3].button("Strikeout-heavy team", key="qp_heavy", on_click=_pick,
                       args=("home_opp", heavy["team_name"]), width="stretch")
        cols[4].button("Contact-heavy team", key="qp_light", on_click=_pick,
                       args=("home_opp", light["team_name"]), width="stretch")

        labels = {p["id"]: f"{p['name']} ({p['games_started']} starts)" for p in ctx.starters}
        c1, c2 = st.columns(2)
        pitcher_id = c1.selectbox(
            "Pitcher", pitcher_options, key="home_pitcher", placeholder="Type a name, or use a quick pick",
            format_func=lambda pid: "" if pid is None else labels[pid])
        opponent = c2.selectbox(
            "Opponent", opponent_options, key="home_opp", placeholder="Pick a team, or use a quick pick",
            format_func=lambda name: "" if name is None else name)

        if pitcher_id is None or opponent is None:
            st.info("Choose a pitcher and an opponent to see the forecast appear here.")
            return
        _mini_forecast(ctx, pages, ctx.pitcher(pitcher_id), opponent)


def _mini_forecast(ctx, pages, pitcher, opponent):
    if opponent == state.LEAGUE_AVERAGE:
        opp_k, opp_pa = ctx.league_k, ctx.league_pa
    else:
        team = ctx.team(opponent)
        opp_k, opp_pa = team["strikeouts"], team["plate_appearances"]
    n, source, used, _ = ctx.default_workload(pitcher["id"])
    try:
        fc = model.build_forecast(pitcher["strikeouts"], pitcher["batters_faced"], opp_k, opp_pa,
                                  ctx.league_k, ctx.league_pa, n, state.DEFAULT_LINE)
    except model.ModelInputError as error:
        st.error(str(error))
        return

    left, right = st.columns([2, 3])
    with left:
        st.metric("Expected strikeouts", f"{fc.expected:.2f}",
                  delta=f"{fc.adjustment_effect:+.2f} vs. pitcher-only ({fc.baseline_expected:.2f})", delta_color="off")
        st.metric(f"Chance of over {fc.line:.1f}", f"{fc.p_over:.1%}")
    right.plotly_chart(charts.mini_probability_chart(fc), width="stretch")

    workload = (f"the average of the pitcher's last {used} starts" if source == "api"
                else "a manual assumption, not derived from the API")
    if model.is_small_sample(pitcher["batters_faced"]):
        st.warning(f"Small sample: this pitcher faced only {pitcher['batters_faced']} batters in {ctx.season}.")
    st.caption(f"Assumes {n} batters faced ({workload}) and a hypothetical line of {fc.line:.1f}, using the opponent's "
               "season-long team stats. Change any of it in the Forecast Lab.")
    if st.button("Open the full analysis →", type="primary", key="home_open"):
        state.choose_pitcher(pitcher["id"])
        state.choose_opponent(opponent)
        st.switch_page(pages["lab"])


# ------------------------------------------------------------- today teaser

def _today_teaser(ctx, pages):
    """A live glimpse of today's slate. It needs only the (fast, cached) schedule, and quietly
    disappears if there is no slate or it can't be loaded, since it is a teaser, not a feature."""
    try:
        schedule = ctx.slate(date.today().isoformat())
    except api.ApiError:
        return
    if not schedule or not schedule["games"]:
        return
    games = schedule["games"]
    upcoming = [g for g in games if slate.is_playable_preview(g)]
    sides = [g[s] for g in games for s in ("away", "home")]
    posted = sum(1 for x in sides if x["lineup"])
    shown = (upcoming or games)[:3]

    rows = "".join(
        f'<div class="game-row"><span class="teams">{escape(g["away"]["team_name"])} @ {escape(g["home"]["team_name"])}</span>'
        f'<span class="meta">{escape(g["away"]["pitcher_name"] or "TBD")} vs. {escape(g["home"]["pitcher_name"] or "TBD")}'
        f' · {escape(ui.local_time(g["start"]))}</span></div>'
        for g in shown
    )
    label = f"Saved slate · {schedule['date']}" if ctx.offline else "On the slate today"
    ui.eyebrow("Right now", before_heading=False)
    st.markdown(
        f'<div class="today-card fade-up"><div class="pill"><span class="dot"></span>{escape(label)}</div>'
        f'<div class="big">{len(games)} games · {len(upcoming)} still to play</div>'
        f'<div class="muted">Lineups are posted for {posted} of {len(sides)} teams. Coming up:</div>{rows}</div>',
        unsafe_allow_html=True,
    )
    if st.button("See which bats could help or hurt each pitcher →", type="primary", key="home_today"):
        st.switch_page(pages["today"])


# ------------------------------------------------------------------ leaders

def _leaders(ctx, pages, in_progress):
    ui.eyebrow("Explore")
    st.markdown("### Who strikes out, and who gets struck out")
    mode = st.segmented_control("View", ["Pitchers", "Offenses"], default="Pitchers", key="home_leaders",
                                label_visibility="collapsed") or "Pitchers"
    if mode == "Pitchers":
        pool = [p for p in ctx.starters if p["games_started"] >= 10] or ctx.starters
        top = sorted(pool, key=lambda p: -p["k_rate"])[:10]
        labels = [p["name"] for p in top]
        hover = [f"<b>{escape(p['name'])}</b><br>{p['k_rate']:.1%} strikeout rate<br>{p['strikeouts']} K in "
                 f"{p['batters_faced']} batters faced · {p['games_started']} starts" for p in top]
        rates, color = [p["k_rate"] for p in top], charts.OVER_COLOR
        st.caption("The 10 highest strikeout rates (strikeouts ÷ batters faced) among pitchers with 10 or more starts. Hover a bar for details.")
    else:
        top = sorted(ctx.teams, key=lambda t: -t["k_rate"])[:10]
        labels = [t["team_name"] for t in top]
        hover = [f"<b>{escape(t['team_name'])}</b><br>{t['k_rate']:.1%} strikeout rate<br>{t['strikeouts']:,} K in "
                 f"{t['plate_appearances']:,} plate appearances" for t in top]
        rates, color = [t["k_rate"] for t in top], charts.NAVY
        st.caption("The 10 offenses that strike out most often (strikeouts ÷ plate appearances). Facing one of these raises a pitcher's forecast.")
    st.plotly_chart(charts.leaders_chart(labels, rates, hover, ctx.league_rate, color), width="stretch")

    st.markdown(f"### Top strikeout pitchers of {ctx.season}" + (" so far" if in_progress else ""))
    st.caption("Pick one to jump straight into a forecast, or browse everyone.")
    top6 = sorted(ctx.starters, key=lambda p: -p["strikeouts"])[:6]
    for row_start in (0, 3):
        for column, pitcher in zip(st.columns(3), top6[row_start:row_start + 3]):
            with column.container(border=True):
                st.markdown(f'<div class="pitcher-name">{escape(pitcher["name"])}</div>', unsafe_allow_html=True)
                st.caption(
                    f"{pitcher['strikeouts']} strikeouts · {pitcher['k_rate']:.1%} of batters faced · "
                    f"{pitcher['games_started']} starts"
                )
                if st.button("Forecast →", key=f"home_top_{pitcher['id']}", width="stretch"):
                    state.choose_pitcher(pitcher["id"])
                    st.switch_page(pages["lab"])


# ------------------------------------------------------------- how it works

def _how_it_works(pages):
    ui.eyebrow("The basics")
    st.markdown("### How it works")
    steps = [
        ("1", "Browse", "Search the season's starting pitchers and see who racks up the most strikeouts."),
        ("2", "Set the matchup", "Choose an opponent and how many batters you expect the pitcher to face."),
        ("3", "Read the forecast", "See the expected strikeouts, the chance of going over or under a line, and why."),
    ]
    for column, (number, title, text) in zip(st.columns(3), steps):
        with column.container(border=True):
            st.markdown(f'<div class="step-number">{number}</div>', unsafe_allow_html=True)
            st.markdown(f"**{title}**")
            st.caption(text)
    st.page_link(pages["about"], label="Read the full explanation", icon=":material/menu_book:")
