"""views/about.py -- the model explained in plain English, plus what the data can and can't do."""

import streamlit as st

import model
import ui

# Shared with the "How this model works" panel in the Lab, so the two never disagree.
ASSUMPTIONS_MD = (
    "- **Fixed workload.** The model treats batters faced as a number you choose. In real games a pitcher "
    "can be pulled early or go deep depending on how the game unfolds.\n"
    "- **Independent, identical batters.** A binomial model assumes every plate appearance has the same "
    "strikeout probability, independent of the others. Real batters, counts, and times through the order differ.\n"
    "- **Untested matchup formula.** `pitcher_rate x (opponent_rate / league_rate)` and the 1%-60% limits are "
    "simple assumptions, chosen because they are easy to explain. They were not fitted to data or validated.\n"
    "- **Opponent stats.** The Forecast Lab uses the whole team's season, not the confirmed lineup, and includes "
    "players who may have since left. The Today page uses the posted lineup's season totals when there is one, "
    "which still ignores batting order, left/right matchups, rest days, and late lineup changes.\n"
    "- **Season statistics, not projections.** No adjustment for a small sample, aging, injuries, ballpark, "
    "weather, umpire, or left/right matchups.\n"
    "- **Not validated.** This project does not include a backtest, so nothing here should be read as evidence "
    "of accuracy or of an advantage over sportsbooks. The line is purely hypothetical."
)


def render(ctx, pages):
    ui.page_header("How it works", "The model, the data, and the fine print, in plain English.")

    st.markdown("### The idea")
    st.write(
        "Every batter a pitcher faces either strikes out or doesn't. If we pretend every batter has the same chance "
        "**p** of striking out, and batters don't affect each other, then the number of strikeouts in **N** batters "
        "behaves like flipping a weighted coin N times and counting heads. That is a *binomial distribution*, and it "
        "lets us work out the chance of every possible strikeout total."
    )

    st.markdown("### Where p comes from")
    st.write("Three rates, each computed from raw counts in the MLB data:")
    st.code(
        "pitcher_rate  = pitcher strikeouts / batters faced\n"
        "opponent_rate = opponent batting strikeouts / plate appearances\n"
        "league_rate   = all MLB batting strikeouts / all MLB plate appearances\n"
        "\n"
        "p = pitcher_rate * (opponent_rate / league_rate)     # limited to 1%-60%",
        language="text",
    )
    st.write(
        "If the opponent strikes out *more* than the league average, the ratio is above 1 and p goes up. If they strike "
        "out *less*, p goes down. Against a league-average team, p is just the pitcher's own rate."
    )

    st.markdown("### What the numbers mean")
    st.markdown(
        "- **Expected strikeouts:** N x p, the average outcome if the model were repeated many times.\n"
        "- **Over / under a line:** for a line like 5.5, *over* means 6 or more strikeouts and *under* means 5 or fewer. "
        "Half-integers are used so there are never ties.\n"
        "- **Central 80% interval:** the range from the 10th to the 90th percentile of the model's distribution. "
        "It describes the *model*, not real games.\n"
        "- **Pitcher-only baseline:** the forecast if the opponent were ignored, so you can see what the opponent changed.\n"
        "- **Workload sensitivity:** how the answer changes if the pitcher faces more or fewer batters. It shows "
        "alternative assumptions, not uncertainty.\n"
        "- **K rate:** strikeouts divided by batters faced (or plate appearances for a team)."
    )

    st.markdown("### Assumptions and limitations")
    st.markdown(ASSUMPTIONS_MD)

    st.markdown("### Today's games and the batters")
    st.write(
        "The Today page runs the same model for every probable starter on a day's schedule. Once a team's lineup is "
        "posted, the opponent rate comes from those nine batters (their season strikeouts divided by their plate "
        "appearances, *added up* across the lineup rather than averaged) instead of the whole team. A lineup full of "
        "strikeout-prone bats raises the forecast above that pitcher's own season average (the bats **help**); a "
        "contact-heavy lineup lowers it (the bats **hurt**). Until a lineup is posted, it falls back to the team's rate "
        "and says so. Probable pitchers can change before first pitch, and the page can't tell you what is a good bet: "
        "it has no sportsbook lines and the formula has never been tested against real results."
    )

    st.markdown("### The data")
    st.write(
        "All statistics come from the public MLB Stats API, which needs no key. The season you select supplies "
        "every number. The app opens on the current season, which may still be in progress (its numbers then change "
        "daily); choose an earlier season in the sidebar for complete, final numbers. "
        "The default workload comes from the pitcher's last five "
        "starts that season; if a game log isn't available, the app says it is using a manual assumption instead. "
        "The model uses **batters faced**, never innings pitched, because baseball's `6.1` innings means 6 and one third, "
        "not 6.1."
    )
    st.info(
        "Strikeout Lab is an educational statistics project. It is not a betting system and does not claim to be "
        "accurate or to beat any sportsbook."
    )
