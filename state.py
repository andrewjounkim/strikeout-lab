"""state.py -- what the app remembers as you move between pages.

Streamlit forgets a widget's value when you leave the page that draws it. So we
keep our own copies ("sel_*" keys) that survive page changes, and widgets copy
their value into them when you change them.
"""

import streamlit as st

LEAGUE_AVERAGE = "League average (no opponent effect)"
DEFAULT_LINE = 5.5


def init():
    """Give every remembered value a starting point (only the first time)."""
    st.session_state.setdefault("sel_pitcher", None)   # a pitcher's ID, or None = nothing chosen yet
    st.session_state.setdefault("sel_opp", None)       # a team name / LEAGUE_AVERAGE, or None
    st.session_state.setdefault("sel_line", DEFAULT_LINE)
    st.session_state.setdefault("bf_choice", {})       # slider values, remembered per pitcher


def sync(persist_key, widget_key):
    """on_change callback: copy a widget's new value into its remembered copy."""
    st.session_state[persist_key] = st.session_state[widget_key]


def bind(persist_key, widget_key):
    """Before drawing a widget, load its remembered value (if it has been reset)."""
    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state[persist_key]


def choose_pitcher(pitcher_id):
    st.session_state["sel_pitcher"] = pitcher_id
    st.session_state.pop("w_pitcher", None)   # make the Lab's dropdown reload from sel_pitcher


def choose_opponent(name):
    st.session_state["sel_opp"] = name
    st.session_state.pop("w_opp", None)


def clear_selection():
    choose_pitcher(None)
    choose_opponent(None)


def remember_workload(widget_key):
    st.session_state["bf_choice"][widget_key] = st.session_state[widget_key]


def drop_unavailable_pitcher(available_ids):
    """If the chosen pitcher isn't in the newly selected season, forget them. True if so."""
    pid = st.session_state["sel_pitcher"]
    if pid is not None and pid not in available_ids:
        choose_pitcher(None)
        return True
    return False
