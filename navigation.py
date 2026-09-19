"""navigation.py -- builds the four pages and the navigation bar.

Kept separate from app.py so tests can start the app on any page.
"""

import streamlit as st

from views import about, browse, home, lab, today


def run(ctx, start="home"):
    """Show the navigation bar and the page named by `start` (the home page for real visitors)."""
    pages = {}
    pages["home"] = st.Page(lambda: home.render(ctx, pages), title="Home", icon=":material/home:",
                            url_path="home", default=(start == "home"))
    pages["today"] = st.Page(lambda: today.render(ctx, pages), title="Today's Games", icon=":material/today:",
                             url_path="today", default=(start == "today"))
    pages["browse"] = st.Page(lambda: browse.render(ctx, pages), title="Browse", icon=":material/search:",
                              url_path="browse", default=(start == "browse"))
    pages["lab"] = st.Page(lambda: lab.render(ctx, pages), title="Forecast Lab", icon=":material/science:",
                           url_path="lab", default=(start == "lab"))
    pages["about"] = st.Page(lambda: about.render(ctx, pages), title="How it works", icon=":material/menu_book:",
                             url_path="about", default=(start == "about"))
    st.navigation(list(pages.values()), position="top").run()
