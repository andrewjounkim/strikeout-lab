"""charts.py -- the two Plotly charts on the Forecast Lab page."""

import plotly.graph_objects as go

import model

OVER_COLOR, UNDER_COLOR = "#e8590c", "#9fb0cc"
NAVY = "#1f4e8c"
WORKLOAD_MIN, WORKLOAD_MAX = model.WORKLOAD_MIN, model.WORKLOAD_MAX


def _style(fig):
    """Match the app's look: Inter text, transparent background so the page shows through, soft gridlines."""
    fig.update_layout(
        font=dict(family="Inter, sans-serif", color="#14213d"),
        title_font=dict(family="Barlow Condensed, sans-serif", size=24, color="#0f2a4a"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(gridcolor="#e4eaf5", zerolinecolor="#cfdcf2")
    fig.update_yaxes(gridcolor="#e4eaf5", zerolinecolor="#cfdcf2")
    return fig


def probability_chart(fc):
    """Bar chart: probability of every strikeout total, with the 'over' totals highlighted."""
    line = fc.line
    threshold = model.min_strikeouts_to_go_over(line)
    shown = [k for k, pr in zip(fc.ks, fc.probabilities) if pr >= 0.0005]   # hide the ~0% tails
    x_max = max(max(shown), threshold) + 1.5
    under = [(k, pr * 100) for k, pr in zip(fc.ks, fc.probabilities) if k < threshold]
    over = [(k, pr * 100) for k, pr in zip(fc.ks, fc.probabilities) if k >= threshold]

    fig = go.Figure()
    for name, points, color in ((f"Under {line:.1f}", under, UNDER_COLOR), (f"Over {line:.1f}", over, OVER_COLOR)):
        fig.add_bar(
            x=[k for k, _ in points], y=[pr for _, pr in points], name=name, marker_color=color,
            hovertemplate="%{x} strikeouts: %{y:.1f}%<extra></extra>",
        )
    fig.add_vline(x=line, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="Chance of each strikeout total", xaxis_title="Strikeouts", yaxis_title="Probability (%)",
        xaxis=dict(range=[-0.5, x_max], dtick=1), barmode="overlay", height=420,
        margin=dict(t=50, b=90), legend=dict(orientation="h", y=-0.28),
    )
    return _style(fig)


def sensitivity_chart(fc):
    """Line chart: P(over the line) if the pitcher faced more or fewer batters."""
    workloads = list(range(WORKLOAD_MIN, WORKLOAD_MAX + 1))
    curve = [pr * 100 for pr in model.sensitivity_curve(fc.matchup.p, fc.line, workloads)]
    fig = go.Figure()
    fig.add_scatter(
        x=workloads, y=curve, mode="lines+markers", name=f"P(over {fc.line:.1f})", line=dict(color=OVER_COLOR),
        hovertemplate="%{x} batters faced: %{y:.1f}% over<extra></extra>",
    )
    fig.add_scatter(
        x=[fc.n], y=[fc.p_over * 100], mode="markers", name="Your selection",
        marker=dict(size=14, color="black", symbol="diamond"),
        hovertemplate="Your selection: %{y:.1f}% over<extra></extra>",
    )
    fig.update_layout(
        title=f"If the workload changes: chance of over {fc.line:.1f}", xaxis_title="Batters faced",
        yaxis_title="Probability of over (%)", yaxis=dict(range=[0, 100]), height=420,
        margin=dict(t=50, b=90), legend=dict(orientation="h", y=-0.28),
    )
    return _style(fig)


def mini_probability_chart(fc):
    """A compact version of the probability chart for the home page: no title or legend, just the shape."""
    threshold = model.min_strikeouts_to_go_over(fc.line)
    shown = [k for k, pr in zip(fc.ks, fc.probabilities) if pr >= 0.0005]
    colors = [OVER_COLOR if k >= threshold else UNDER_COLOR for k in fc.ks]
    fig = go.Figure(go.Bar(
        x=fc.ks, y=[pr * 100 for pr in fc.probabilities], marker_color=colors,
        hovertemplate="%{x} strikeouts: %{y:.1f}%<extra></extra>",
    ))
    fig.add_vline(x=fc.line, line_dash="dash", line_color="gray")
    fig.update_layout(
        height=270, margin=dict(t=10, b=40, l=40, r=10), showlegend=False, bargap=0.15,
        xaxis=dict(range=[-0.5, max(max(shown), threshold) + 1.5], dtick=1, title="Strikeouts"),
        yaxis=dict(title="Chance (%)"),
    )
    return _style(fig)


def leaders_chart(labels, rates, hover, league_rate, color=OVER_COLOR):
    """Horizontal bars of strikeout rates (highest at the top) with the league average marked."""
    fig = go.Figure(go.Bar(
        x=[r * 100 for r in reversed(rates)], y=list(reversed(labels)), orientation="h", marker_color=color,
        customdata=list(reversed(hover)), hovertemplate="%{customdata}<extra></extra>",
        text=[f"{r:.1%}" for r in reversed(rates)], textposition="outside", cliponaxis=False,
    ))
    fig.add_vline(x=league_rate * 100, line_dash="dash", line_color=NAVY,
                  annotation_text=f"League average {league_rate:.1%}", annotation_position="top",
                  annotation_font_color=NAVY)
    top = max(rates) * 100
    fig.update_layout(
        height=410, margin=dict(t=34, b=40, l=10, r=40), showlegend=False,
        xaxis=dict(title="Strikeout rate (%)", range=[0, top * 1.18]), yaxis=dict(automargin=True),
    )
    return _style(fig)
