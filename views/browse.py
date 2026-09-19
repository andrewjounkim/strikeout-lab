"""views/browse.py -- search and sort every pitcher and team, then send one to the Lab."""

from html import escape

import pandas as pd
import streamlit as st

import model
import state
import ui

SIZE_OPTIONS = {"10+ starts": 10, "20+ starts": 20, "All starters": 1}
SORT_OPTIONS = {
    "Most strikeouts": ("Strikeouts", False),
    "Highest strikeout rate": ("K rate", False),
    "Most starts": ("Starts", False),
    "Name (A to Z)": ("Pitcher", True),
}


def render(ctx, pages):
    ui.page_header("Browse", f"Explore the {ctx.season} season, then send a pitcher or team to the Forecast Lab.")
    pitchers_tab, teams_tab = st.tabs(["Pitchers", "Teams"])
    with pitchers_tab:
        _pitchers(ctx, pages)
    with teams_tab:
        _teams(ctx, pages)


def _selected_row(event, frame):
    """The one row the user clicked in a table, or None."""
    rows = event.selection.rows
    return frame.iloc[rows[0]] if rows else None


def _pitchers(ctx, pages):
    c1, c2, c3 = st.columns([3, 2, 2])
    query = c1.text_input("Search by name", placeholder="e.g. Skubal", key="browse_query")
    size = c2.selectbox("Sample size", list(SIZE_OPTIONS), key="browse_size",
                        help="Pitchers with more starts have more reliable strikeout rates.")
    sort_label = c3.selectbox("Sort by", list(SORT_OPTIONS), key="browse_sort")

    rows = [p for p in ctx.starters
            if p["games_started"] >= SIZE_OPTIONS[size] and query.strip().lower() in p["name"].lower()]
    frame = pd.DataFrame({
        "id": [p["id"] for p in rows],
        "Pitcher": [p["name"] for p in rows],
        "Starts": [p["games_started"] for p in rows],
        "Batters faced": [p["batters_faced"] for p in rows],
        "Strikeouts": [p["strikeouts"] for p in rows],
        "K rate": [p["k_rate"] * 100 for p in rows],
        "Note": ["small sample" if model.is_small_sample(p["batters_faced"]) else "" for p in rows],
    })
    column, ascending = SORT_OPTIONS[sort_label]
    frame = frame.sort_values(column, ascending=ascending, kind="stable").reset_index(drop=True)

    st.caption(f"Showing {len(frame)} of {len(ctx.starters)} starting pitchers. "
               f"K rate = strikeouts ÷ batters faced. Click a row to select it.")
    if frame.empty:
        st.info("No pitchers match. Try clearing the search or choosing a smaller sample size.")
        return

    event = st.dataframe(
        frame.drop(columns="id"), key="browse_pitchers", on_select="rerun", selection_mode="single-row",
        hide_index=True, width="stretch", height=420,
        column_config={
            "K rate": st.column_config.ProgressColumn("K rate", format="%.1f%%", min_value=0, max_value=40),
            "Batters faced": st.column_config.NumberColumn(format="%d"),
        },
    )
    picked = _selected_row(event, frame)
    if picked is None:
        st.info("Select a pitcher in the table above to continue.")
        return
    with st.container(border=True):
        st.markdown(f'<div class="pitcher-name">{escape(picked["Pitcher"])}</div>', unsafe_allow_html=True)
        st.caption(f"{int(picked['Strikeouts'])} strikeouts · {picked['K rate']:.1f}% K rate · {int(picked['Starts'])} starts")
        if st.button(f"Forecast {picked['Pitcher']} →", type="primary"):
            state.choose_pitcher(int(picked["id"]))
            st.switch_page(pages["lab"])


def _teams(ctx, pages):
    st.caption(
        f"How often each team's batters strike out. The league average in {ctx.season} is {ctx.league_rate:.1%}. "
        "Teams that strike out more raise a pitcher's forecast. Click a row to select it."
    )
    frame = pd.DataFrame({
        "Team": [t["team_name"] for t in ctx.teams],
        "Strikeouts": [t["strikeouts"] for t in ctx.teams],
        "Plate appearances": [t["plate_appearances"] for t in ctx.teams],
        "K rate": [t["k_rate"] * 100 for t in ctx.teams],
        "vs. league": [t["vs_league"] * 100 for t in ctx.teams],
    }).sort_values("K rate", ascending=False, kind="stable").reset_index(drop=True)

    event = st.dataframe(
        frame, key="browse_teams", on_select="rerun", selection_mode="single-row", hide_index=True,
        width="stretch", height=420,
        column_config={
            "K rate": st.column_config.ProgressColumn("K rate", format="%.1f%%", min_value=0, max_value=30),
            "vs. league": st.column_config.NumberColumn("vs. league", format="%+.1f%%",
                                                        help="How much more (+) or less (-) often this team strikes out than the league average."),
            "Plate appearances": st.column_config.NumberColumn(format="%d"),
        },
    )
    picked = _selected_row(event, frame)
    if picked is None:
        st.info("Select a team in the table above to use it as the opponent.")
        return
    with st.container(border=True):
        st.markdown(f'<div class="pitcher-name">{escape(picked["Team"])}</div>', unsafe_allow_html=True)
        st.caption(f"{picked['K rate']:.1f}% K rate ({picked['vs. league']:+.1f}% vs. the league average)")
        if st.button(f"Use {picked['Team']} as the opponent →", type="primary"):
            state.choose_opponent(picked["Team"])
            st.switch_page(pages["lab"])
