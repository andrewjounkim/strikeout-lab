"""app.py -- the entry point for Strikeout Lab.  Run with:  streamlit run app.py

This file is short on purpose. It sets up the page, loads the data once
(context.py), and shows a navigation bar with four pages:

    Home     views/home.py     mission statement + top pitchers
    Today    views/today.py    today's games: who the opposing bats help or hurt
    Browse   views/browse.py   search and sort pitchers and teams
    Lab      views/lab.py      pick a matchup and read the forecast
    About    views/about.py    the model explained in plain English

How Streamlit works, in one paragraph: the whole script re-runs from top to
bottom every time you click something. That is why API calls are cached in
context.py: the first run fetches, and later runs reuse the saved answer.
The math lives in model.py and the API code in api.py.
"""

import streamlit as st

import context
import navigation
import state
import ui

st.set_page_config(page_title="Strikeout Lab", page_icon="⚾", layout="wide")
ui.inject_css()
state.init()
ctx = context.setup()   # draws the sidebar and loads the season's data (or stops with a clear error)

navigation.run(ctx)   # the Home page is shown first
