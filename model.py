"""model.py -- the math behind Strikeout Lab.

This file has NO network calls and NO Streamlit code. It only turns numbers
into probabilities, which makes it easy to read and easy to test.

The idea, in plain language
---------------------------
Every batter a pitcher faces is either a strikeout or not. If we pretend:
  * every batter has the same chance p of striking out, and
  * batters are independent of each other,
then the number of strikeouts in N batters follows a Binomial(N, p)
distribution (like flipping a weighted coin N times and counting heads).

The only real question is what p should be. We build it from three rates:
  pitcher_rate  = pitcher strikeouts / batters faced
  opponent_rate = the opponent's batting strikeouts / plate appearances
  league_rate   = all MLB batting strikeouts / all MLB plate appearances

and combine them with a simple matchup adjustment:
  p_raw = pitcher_rate * (opponent_rate / league_rate)

If the opponent strikes out MORE than the league average, the ratio is above 1
and p goes up; if they strike out LESS, p goes down. This is an assumption I
chose because it is easy to explain. It was NOT fitted to data or validated.
"""

import math
from dataclasses import dataclass

from scipy.stats import binom

# Modeling assumption: keep p in a sane range so one weird stat line
# (say, a pitcher with 1 batter faced) can't produce an absurd forecast.
RATE_MIN = 0.01
RATE_MAX = 0.60

# "Central 80%" means we cut off the lowest 10% and highest 10% of outcomes.
INTERVAL_MASS = 0.80

# A pitcher with fewer batters faced than this has a very noisy strikeout rate.
SMALL_SAMPLE_BATTERS_FACED = 100

# Workload (batters faced) limits used by the sliders and charts, and the labeled
# manual fallback used ONLY when a pitcher's recent starts aren't available.
WORKLOAD_MIN, WORKLOAD_MAX = 9, 36
MANUAL_WORKLOAD = 24

# Lineups: a posted lineup is used only if at least this many batters have stats,
# and a batter with fewer plate appearances than LOW_PA has a very noisy rate.
MIN_LINEUP_BATTERS = 7
LOW_PA = 100


class ModelInputError(ValueError):
    """The inputs can't produce a trustworthy answer (missing data, divide by zero...)."""


# ---------------------------------------------------------------- rates

def safe_rate(strikeouts, opportunities, name):
    """strikeouts / opportunities, but refuse to guess when the data is bad.

    `opportunities` is batters faced (for a pitcher) or plate appearances
    (for a batting team). `name` is only used to make error messages clear.
    """
    if strikeouts is None or opportunities is None:
        raise ModelInputError(f"{name}: the API did not provide the counts needed.")
    if opportunities <= 0:
        raise ModelInputError(
            f"{name}: 0 batters faced / plate appearances, so a rate can't be computed."
        )
    if strikeouts < 0 or strikeouts > opportunities:
        raise ModelInputError(f"{name}: {strikeouts} strikeouts in {opportunities} is impossible.")
    return strikeouts / opportunities


def league_totals(team_rows):
    """Add up strikeouts and plate appearances across every team.

    We SUM the raw counts (rather than averaging the 30 teams' percentages) so a
    team with more plate appearances counts for more, as it should.
    """
    if not team_rows:
        raise ModelInputError("No team batting data, so a league average can't be computed.")
    strikeouts = sum(row["strikeouts"] for row in team_rows)
    plate_appearances = sum(row["plate_appearances"] for row in team_rows)
    return strikeouts, plate_appearances


@dataclass(frozen=True)
class LineupSummary:
    strikeouts: int
    plate_appearances: int
    n_batters: int       # batters that had usable stats
    n_low_sample: int    # of those, how many have fewer than LOW_PA plate appearances

    @property
    def rate(self):
        return self.strikeouts / self.plate_appearances


def summarize_lineup(batters):
    """Pool a lineup's raw counts into one strikeout rate, or None if too few batters have stats.

    `batters` is a list of dicts with "strikeouts" and "plate_appearances" (or None for a batter
    we have no stats for, such as a call-up who hasn't batted yet). Like the league rate, we ADD
    the raw counts rather than averaging the batters' percentages, so a regular with 600 plate
    appearances counts for more than a bench bat with 40.
    """
    usable = [b for b in batters if b and b.get("plate_appearances")]
    if len(usable) < MIN_LINEUP_BATTERS:
        return None
    return LineupSummary(
        strikeouts=sum(b["strikeouts"] for b in usable),
        plate_appearances=sum(b["plate_appearances"] for b in usable),
        n_batters=len(usable),
        n_low_sample=sum(1 for b in usable if b["plate_appearances"] < LOW_PA),
    )


def rate_standard_error(rate, opportunities):
    """Rough uncertainty in a rate: sqrt(r * (1 - r) / n). Shrinks as the sample grows."""
    return math.sqrt(rate * (1 - rate) / opportunities)


def is_small_sample(batters_faced):
    return batters_faced < SMALL_SAMPLE_BATTERS_FACED


# -------------------------------------------------------------- matchup

@dataclass(frozen=True)
class Matchup:
    pitcher_rate: float
    opponent_rate: float
    league_rate: float
    p_raw: float   # the formula's answer, before clamping
    p: float       # the value actually used (after clamping)

    @property
    def clipped(self):
        return self.p != self.p_raw


def matchup(pitcher_rate, opponent_rate, league_rate):
    """Combine the three rates into the per-batter strikeout probability p."""
    if league_rate <= 0:
        raise ModelInputError("League strikeout rate is zero, so the matchup can't be computed.")
    p_raw = pitcher_rate * (opponent_rate / league_rate)
    p = min(max(p_raw, RATE_MIN), RATE_MAX)
    return Matchup(pitcher_rate, opponent_rate, league_rate, p_raw, p)


# ---------------------------------------------------------------- lines

def validate_line(line):
    """A valid line is a half-integer (0.5, 1.5, ... 5.5 ...), so there are never ties."""
    try:
        value = float(line)
    except (TypeError, ValueError):
        raise ModelInputError("The strikeout line must be a number.") from None
    is_half_integer = math.isfinite(value) and value >= 0.5 and abs((value - 0.5) - round(value - 0.5)) < 1e-9
    if not is_half_integer:
        raise ModelInputError(
            "The strikeout line must be a half-integer such as 3.5, 4.5, or 5.5 (so it can't tie)."
        )
    return value


def min_strikeouts_to_go_over(line):
    """The smallest whole number of strikeouts that beats the line. 5.5 -> 6."""
    return math.floor(validate_line(line)) + 1


# --------------------------------------------------------- distribution

def strikeout_distribution(n, p):
    """Return (ks, probabilities): P(K = k) for every k from 0 through n."""
    if n < 1:
        raise ModelInputError("Batters faced must be at least 1.")
    ks = list(range(n + 1))
    return ks, [float(x) for x in binom.pmf(ks, n, p)]


def prob_over(n, p, line):
    """P(K >= threshold). For a 5.5 line that is P(K >= 6)."""
    threshold = min_strikeouts_to_go_over(line)
    return float(binom.sf(threshold - 1, n, p))  # sf(x) = P(K > x)


def prob_under(n, p, line):
    """P(K <= threshold - 1). For a 5.5 line that is P(K <= 5)."""
    threshold = min_strikeouts_to_go_over(line)
    return float(binom.cdf(threshold - 1, n, p))  # cdf(x) = P(K <= x)


def central_interval(n, p, mass=INTERVAL_MASS):
    """The whole-number range from the 10th to the 90th percentile of the model.

    Strikeouts come in whole numbers, so the range usually covers a bit MORE
    than 80%; we also return the actual coverage so we can show it honestly.
    """
    tail = (1 - mass) / 2
    low = int(binom.ppf(tail, n, p))
    high = int(binom.ppf(1 - tail, n, p))
    coverage = float(binom.cdf(high, n, p) - binom.cdf(low - 1, n, p))
    return low, high, coverage


def sensitivity_curve(p, line, batters_faced_values):
    """P(over the line) for a range of possible workloads, holding p fixed."""
    return [prob_over(n, p, line) for n in batters_faced_values]


# ------------------------------------------------------------- workload

def suggest_workload(starts, how_many=5):
    """Average batters faced over the last `how_many` starts.

    `starts` is a list of dicts (oldest first) with a "batters_faced" key.
    Returns (rounded_average, number_of_starts_used), or None if there are none.
    """
    recent = [s["batters_faced"] for s in starts[-how_many:]]
    if not recent:
        return None
    return int(sum(recent) / len(recent) + 0.5), len(recent)


# ------------------------------------------------------------- forecast

@dataclass(frozen=True)
class Forecast:
    n: int
    line: float
    matchup: Matchup
    expected: float            # N * p
    baseline_expected: float   # N * pitcher_rate (no opponent adjustment)
    p_over: float
    p_under: float
    interval_low: int
    interval_high: int
    interval_coverage: float
    ks: list
    probabilities: list

    @property
    def adjustment_effect(self):
        """How many strikeouts the opponent adjustment added (or removed)."""
        return self.expected - self.baseline_expected


def build_forecast(pitcher_k, pitcher_bf, opponent_k, opponent_pa, league_k, league_pa, n, line):
    """Run the whole model from raw API counts to a finished Forecast."""
    line = validate_line(line)
    pitcher_rate = safe_rate(pitcher_k, pitcher_bf, "Pitcher strikeout rate")
    opponent_rate = safe_rate(opponent_k, opponent_pa, "Opponent strikeout rate")
    league_rate = safe_rate(league_k, league_pa, "League strikeout rate")

    m = matchup(pitcher_rate, opponent_rate, league_rate)
    ks, probs = strikeout_distribution(n, m.p)
    low, high, coverage = central_interval(n, m.p)
    return Forecast(
        n=n,
        line=line,
        matchup=m,
        expected=n * m.p,
        baseline_expected=n * pitcher_rate,
        p_over=prob_over(n, m.p, line),
        p_under=prob_under(n, m.p, line),
        interval_low=low,
        interval_high=high,
        interval_coverage=coverage,
        ks=ks,
        probabilities=probs,
    )
