"""ui.py -- the look of the app: CSS (background, cards, animations) and a few reusable pieces.

Fonts and base colors come from .streamlit/config.toml; everything here is layered on top.
All motion respects the "reduce motion" setting, and nothing depends on it to be readable.
"""

from datetime import datetime
from html import escape

import streamlit as st

import api

# A baseball: white ball outline with two curved, dashed "stitch" seams.
BASEBALL_SVG = """<svg class="ball" viewBox="0 0 200 200" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
  <circle cx="100" cy="100" r="94" fill="rgba(255,255,255,.07)" stroke="#fff" stroke-width="4"/>
  <path d="M46 20 C86 62 86 138 46 180" fill="none" stroke="#ff8a3d" stroke-width="7" stroke-dasharray="3 11" stroke-linecap="round"/>
  <path d="M154 20 C114 62 114 138 154 180" fill="none" stroke="#ff8a3d" stroke-width="7" stroke-dasharray="3 11" stroke-linecap="round"/>
</svg>"""
# Markdown ends an HTML block at the first blank line, so the SVG must not contain or add any:
BASEBALL_SVG = "".join(line.strip() for line in BASEBALL_SVG.splitlines())

CSS = """
<style>
/* ---------- page background: soft color washes over a faint dot grid ---------- */
.stApp {
    background:
        radial-gradient(rgba(20,33,61,.055) 1px, transparent 1px) 0 0 / 26px 26px,
        radial-gradient(1000px 520px at 6% -6%, rgba(232,89,12,.11), transparent 62%),
        radial-gradient(900px 620px at 102% 2%, rgba(31,78,140,.14), transparent 58%),
        linear-gradient(180deg, #f6f8fc 0%, #ffffff 46%, #f1f5fb 100%);
    background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.6rem; }

/* ---------- animation ---------- */
@keyframes fadeUp { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes heroShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(255,138,61,.65); } 70% { box-shadow: 0 0 0 10px rgba(255,138,61,0); } 100% { box-shadow: 0 0 0 0 rgba(255,138,61,0); } }
.fade-up { animation: fadeUp .7s cubic-bezier(.2,.7,.2,1) both; }
.d1 { animation-delay: .08s; } .d2 { animation-delay: .16s; } .d3 { animation-delay: .24s; } .d4 { animation-delay: .32s; }

/* ---------- hero ---------- */
.hero {
    position: relative; overflow: hidden; color: #fff; border-radius: 26px; margin-bottom: 1.3rem;
    padding: 3rem 3.2rem 2.8rem;
    background: linear-gradient(120deg, #0b1f3a 0%, #16437e 48%, #0f2a4a 100%);
    background-size: 220% 220%; animation: heroShift 16s ease-in-out infinite;
    box-shadow: 0 24px 60px rgba(15,42,74,.28);
}
.hero::before {
    content: ""; position: absolute; inset: 0;
    background: radial-gradient(520px 320px at 88% 12%, rgba(255,138,61,.38), transparent 62%),
                radial-gradient(420px 260px at 0% 100%, rgba(80,140,230,.28), transparent 65%);
}
.hero .ball { position: absolute; right: -60px; top: -60px; width: 380px; opacity: .55; animation: spin 60s linear infinite; }
.hero > *:not(.ball) { position: relative; }
.hero .pill {
    display: inline-flex; align-items: center; gap: .55rem; padding: .35rem .9rem; border-radius: 999px;
    background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22);
    font-size: .78rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
}
.hero .dot { width: 9px; height: 9px; border-radius: 50%; background: #ff8a3d; animation: pulse 2s infinite; }
.hero .title {
    font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: clamp(3.4rem, 8vw, 6.4rem); line-height: .95;
    margin: 1rem 0 .5rem; letter-spacing: -.01em;
    background: linear-gradient(90deg, #ffffff 30%, #ffc79a 100%); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.hero .tagline { font-size: clamp(1.05rem, 2.2vw, 1.5rem); font-weight: 500; opacity: .95; max-width: 33rem; margin-bottom: 1.4rem; }
.hero .mission {
    font-size: 1.02rem; line-height: 1.65; max-width: 44rem; padding: 1rem 1.3rem;
    background: rgba(255,255,255,.09); border-left: 4px solid #ff8a3d; border-radius: 10px; backdrop-filter: blur(4px);
}
.hero .mission b { color: #ffc79a; }

/* ---------- stat tiles ---------- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1rem; margin: .4rem 0 1.6rem; }
.tile {
    background: #fff; border: 1px solid #dbe3f1; border-radius: 18px; padding: 1.1rem 1.3rem 1.15rem;
    box-shadow: 0 2px 12px rgba(15,42,74,.06); transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
    border-top: 4px solid #e8590c;
}
.tile:hover { transform: translateY(-5px); box-shadow: 0 16px 36px rgba(15,42,74,.14); border-color: #c5d3ea; }
.tile:nth-child(even) { border-top-color: #1f4e8c; }
.tile .value { font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 2.7rem; line-height: 1.05; color: #0f2a4a; }
.tile .value.small { font-size: 2rem; }
.tile .label { color: #5a6b85; font-size: .9rem; margin-top: .2rem; line-height: 1.35; }

/* ---------- today teaser ---------- */
.today-card {
    background: linear-gradient(135deg, #ffffff 0%, #f1f6ff 100%); border: 1px solid #cfdcf2; border-radius: 20px;
    padding: 1.3rem 1.5rem; box-shadow: 0 6px 24px rgba(15,42,74,.08);
}
.today-card .pill {
    display: inline-flex; align-items: center; gap: .5rem; font-size: .74rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: #c2410c;
}
.today-card .dot { width: 9px; height: 9px; border-radius: 50%; background: #e8590c; animation: pulse 2s infinite; }
.today-card .big { font-family: "Barlow Condensed", sans-serif; font-weight: 800; font-size: 2.6rem; line-height: 1.05; color: #0f2a4a; margin: .3rem 0 .1rem; }
.game-row {
    display: flex; justify-content: space-between; gap: 1rem; padding: .55rem 0; border-top: 1px dashed #cfdcf2;
    font-size: .95rem;
}
.game-row .teams { font-weight: 700; color: #0f2a4a; }
.game-row .meta { color: #5a6b85; text-align: right; }

/* ---------- headings and cards ---------- */
.section-eyebrow { text-transform: uppercase; letter-spacing: .14em; font-size: .76rem; font-weight: 700; color: #e8590c; margin: 1.6rem 0 -.5rem; }
.section-eyebrow.spaced { margin-bottom: .6rem; }
.page-header { margin-bottom: .8rem; }
.page-header .title { font-family: "Barlow Condensed", sans-serif; font-size: 3rem; font-weight: 800; line-height: 1.05; margin: 0; color: #0f2a4a; }
.page-header .sub { color: #5a6b85; font-size: 1.08rem; }
.step-number {
    display: inline-flex; align-items: center; justify-content: center; width: 2.1rem; height: 2.1rem; border-radius: 50%;
    background: linear-gradient(135deg, #e8590c, #ff8a3d); color: #fff; font-weight: 700; margin-bottom: .4rem;
    box-shadow: 0 4px 10px rgba(232,89,12,.35);
}
.verdict {
    background: linear-gradient(135deg, #fff7f0 0%, #f2f6fd 100%); border-left: 5px solid #e8590c; border-radius: 12px;
    padding: 1.05rem 1.35rem; font-size: 1.16rem; line-height: 1.6; margin: .4rem 0 1rem; box-shadow: 0 2px 10px rgba(15,42,74,.06);
}
.muted { color: #5a6b85; }
.pitcher-name { font-family: "Barlow Condensed", sans-serif; font-size: 1.5rem; font-weight: 700; line-height: 1.1; color: #0f2a4a; margin-bottom: .15rem; }

[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; box-shadow: 0 2px 12px rgba(15,42,74,.06); transition: box-shadow .2s ease, transform .2s ease; }
[data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"]:hover { box-shadow: 0 14px 32px rgba(15,42,74,.13); transform: translateY(-3px); }
[data-testid="stMetric"] {
    background: #fff; border: 1px solid #dbe3f1; border-radius: 16px; padding: .9rem 1.1rem;
    box-shadow: 0 2px 10px rgba(15,42,74,.05); border-top: 3px solid #e8590c;
}
.stButton > button, [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] { transition: transform .15s ease, box-shadow .15s ease; font-weight: 600; }
.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 18px rgba(15,42,74,.16); }
[data-testid="stTopNav"] a, [data-testid="stTopNavLink"] { font-weight: 600; }

@media (max-width: 640px) {
    .hero { padding: 2rem 1.4rem 1.8rem; border-radius: 20px; }
    .hero .ball { width: 190px; right: -70px; top: -60px; opacity: .3; }
}
@media (prefers-reduced-motion: reduce) {
    .fade-up, .hero, .hero .ball, .hero .dot, .today-card .dot { animation: none !important; }
    .tile, .stButton > button, [data-testid="stVerticalBlockBorderWrapper"] { transition: none !important; }
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(season, offline, in_progress=False):
    """The animated banner at the top of the home page, with the mission statement."""
    source = "Saved offline data" if offline else "Live MLB data"
    season = f"{season} season (in progress)" if in_progress else f"{season} season"
    st.markdown(
        f'<div class="hero fade-up">{BASEBALL_SVG}'
        f'<div class="pill"><span class="dot"></span>{escape(source)} · {escape(season)}</div>'
        '<div class="title">Strikeout Lab</div>'
        '<div class="tagline">See how the pitcher, the opponent, and the workload change the strikeout forecast.</div>'
        '<div class="mission"><b>Our mission:</b> help anyone see, in plain terms, how a pitcher\'s skill and the team they '
        'face shape how many strikeouts to expect, using open MLB data and a model simple enough to '
        'understand in five minutes.</div></div>',
        unsafe_allow_html=True,
    )


def tiles(items):
    """A row of stat tiles. `items` is a list of (value, label, small) tuples; text is escaped."""
    cells = "".join(
        f'<div class="tile fade-up d{min(i + 1, 4)}"><div class="value{" small" if small else ""}">{escape(str(value))}</div>'
        f'<div class="label">{escape(label)}</div></div>'
        for i, (value, label, small) in enumerate(items)
    )
    st.markdown(f'<div class="tiles">{cells}</div>', unsafe_allow_html=True)


def eyebrow(text, before_heading=True):
    """A small orange label above a section. `before_heading=False` is for when a card (not a heading) follows."""
    cls = "section-eyebrow" if before_heading else "section-eyebrow spaced"
    st.markdown(f'<div class="{cls}">{escape(text)}</div>', unsafe_allow_html=True)


def page_header(title, subtitle):
    st.markdown(
        f'<div class="page-header fade-up"><div class="title">{escape(title)}</div><div class="sub">{escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )


def game_time(iso):
    """A UTC start time shown in MLB's own time zone (Eastern), like '7:05 PM'. Callers label it "ET"."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(api.MLB_TZ).strftime("%I:%M %p").lstrip("0")
    except (AttributeError, ValueError):
        return ""
