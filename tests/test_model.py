"""Tests for model.py -- the probability math. Run with:  pytest"""

import math

import pytest

import model


# ------------------------------------------------ probabilities sum to 1

@pytest.mark.parametrize("n, p", [(24, 0.25), (9, 0.01), (36, 0.60), (1, 0.5), (27, 0.3133)])
def test_distribution_sums_to_one(n, p):
    ks, probs = model.strikeout_distribution(n, p)
    assert ks == list(range(n + 1))
    assert math.isclose(sum(probs), 1.0, abs_tol=1e-9)
    assert all(0 <= x <= 1 for x in probs)


# ------------------------------------------- over/under for half-integer lines

def test_over_and_under_for_a_5_5_line_split_at_six_strikeouts():
    n, p = 24, 0.28
    ks, probs = model.strikeout_distribution(n, p)
    # "over 5.5" means 6 or more strikeouts; "under 5.5" means 5 or fewer.
    assert math.isclose(model.prob_over(n, p, 5.5), sum(probs[6:]), abs_tol=1e-12)
    assert math.isclose(model.prob_under(n, p, 5.5), sum(probs[:6]), abs_tol=1e-12)


@pytest.mark.parametrize("line", [0.5, 3.5, 4.5, 5.5, 11.5])
def test_over_plus_under_is_exactly_one_so_there_are_no_pushes(line):
    assert math.isclose(model.prob_over(24, 0.3, line) + model.prob_under(24, 0.3, line), 1.0, abs_tol=1e-12)


def test_threshold_examples():
    assert model.min_strikeouts_to_go_over(5.5) == 6
    assert model.min_strikeouts_to_go_over(4.5) == 5
    assert model.min_strikeouts_to_go_over(0.5) == 1


def test_line_beyond_the_workload_has_zero_chance_of_over():
    # Can't strike out 31 batters if only 24 come up.
    assert model.prob_over(24, 0.5, 30.5) == 0.0
    assert model.prob_under(24, 0.5, 30.5) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [5, 5.0, 5.25, 0, 0.0, -0.5, 4.9, float("nan"), float("inf"), "abc", None])
def test_lines_that_are_not_half_integers_are_rejected(bad):
    with pytest.raises(model.ModelInputError):
        model.validate_line(bad)


def test_more_batters_faced_never_lowers_the_chance_of_over():
    curve = model.sensitivity_curve(0.27, 5.5, range(9, 37))
    assert all(later >= earlier - 1e-12 for earlier, later in zip(curve, curve[1:]))


# --------------------------------------------- the matchup adjustment

def test_league_average_opponent_leaves_the_pitcher_rate_unchanged():
    league = 0.2222
    m = model.matchup(pitcher_rate=0.31, opponent_rate=league, league_rate=league)
    assert m.p == pytest.approx(0.31)
    assert not m.clipped


def test_strikeout_heavy_opponent_raises_p_and_contact_heavy_lowers_it():
    assert model.matchup(0.25, 0.26, 0.22).p > 0.25
    assert model.matchup(0.25, 0.18, 0.22).p < 0.25


def test_extreme_matchups_are_clamped_and_flagged():
    high = model.matchup(0.55, 0.30, 0.20)     # raw = 0.825
    low = model.matchup(0.001, 0.20, 0.20)     # raw = 0.001
    assert high.clipped and high.p == model.RATE_MAX and high.p_raw == pytest.approx(0.825)
    assert low.clipped and low.p == model.RATE_MIN


def test_full_forecast_reports_effect_versus_pitcher_only_baseline():
    # pitcher: 250 K / 800 BF = 0.3125.  opponent: 1300 / 6000 = 0.2167.  league: 40000 / 180000 = 0.2222
    fc = model.build_forecast(250, 800, 1300, 6000, 40000, 180000, n=24, line=5.5)
    assert fc.baseline_expected == pytest.approx(24 * 250 / 800)
    assert fc.expected == pytest.approx(24 * fc.matchup.p)
    assert fc.adjustment_effect == pytest.approx(fc.expected - fc.baseline_expected)
    assert fc.adjustment_effect < 0                      # a below-average-strikeout opponent lowers the forecast
    assert math.isclose(sum(fc.probabilities), 1.0, abs_tol=1e-9)


# ------------------------------------------------ the 80% interval

@pytest.mark.parametrize("n, p", [(24, 0.25), (24, 0.05), (30, 0.4), (9, 0.3)])
def test_central_interval_covers_at_least_80_percent(n, p):
    low, high, coverage = model.central_interval(n, p)
    assert 0 <= low <= high <= n
    assert coverage >= 0.80
    ks, probs = model.strikeout_distribution(n, p)
    assert coverage == pytest.approx(sum(probs[low:high + 1]))     # reported coverage matches the actual mass
    assert low <= n * p <= high                                    # the average sits inside the range


# ------------------------------------- missing / zero-denominator inputs

@pytest.mark.parametrize("strikeouts, opportunities", [(5, 0), (5, None), (None, 100), (0, 0), (5, -3), (-1, 100), (101, 100)])
def test_safe_rate_refuses_missing_zero_or_impossible_counts(strikeouts, opportunities):
    with pytest.raises(model.ModelInputError):
        model.safe_rate(strikeouts, opportunities, "Test rate")


def test_safe_rate_normal_and_zero_strikeouts():
    assert model.safe_rate(50, 200, "x") == 0.25
    assert model.safe_rate(0, 40, "x") == 0.0       # zero strikeouts is valid; only a zero DENOMINATOR is not


def test_league_totals_sum_raw_counts_not_average_the_percentages():
    teams = [
        {"strikeouts": 100, "plate_appearances": 200},    # 50%
        {"strikeouts": 10, "plate_appearances": 800},     # 1.25%
    ]
    k, pa = model.league_totals(teams)
    assert (k, pa) == (110, 1000)
    assert k / pa == pytest.approx(0.11)                  # an unweighted average of the percentages would be ~25.6%


def test_league_totals_with_no_teams_is_an_error():
    with pytest.raises(model.ModelInputError):
        model.league_totals([])


def test_zero_league_rate_and_zero_batters_faced_are_errors():
    with pytest.raises(model.ModelInputError):
        model.matchup(0.3, 0.2, 0.0)
    with pytest.raises(model.ModelInputError):
        model.strikeout_distribution(0, 0.3)


def test_forecast_with_zero_denominator_stops_instead_of_guessing():
    with pytest.raises(model.ModelInputError):
        model.build_forecast(250, 0, 1300, 6000, 40000, 180000, n=24, line=5.5)
    with pytest.raises(model.ModelInputError):
        model.build_forecast(250, 800, 1300, 6000, 40000, 180000, n=24, line=5.0)   # not a half-integer


# ------------------------------------------------------------ workload

def test_suggest_workload_uses_only_the_last_five_starts_and_reports_the_sample_size():
    starts = [{"batters_faced": b} for b in (10, 30, 25, 26, 24, 24, 26)]      # oldest first
    assert model.suggest_workload(starts) == (25, 5)                          # mean of 25, 26, 24, 24, 26 = 25
    assert model.suggest_workload(starts[:2]) == (20, 2)                      # only 2 starts available
    assert model.suggest_workload([]) is None                                 # no starts -> no suggestion


def test_small_sample_flag():
    assert model.is_small_sample(99)
    assert not model.is_small_sample(100)


# ------------------------------------------------------------- lineups

def batter(k, pa):
    return {"strikeouts": k, "plate_appearances": pa}


def test_lineup_rate_pools_the_raw_counts_instead_of_averaging_percentages():
    lineup = [batter(100, 200)] * 1 + [batter(10, 800)] + [batter(50, 250)] * 7
    s = model.summarize_lineup(lineup)
    assert (s.strikeouts, s.plate_appearances) == (100 + 10 + 350, 200 + 800 + 1750)
    assert s.rate == pytest.approx(460 / 2750)
    assert s.rate != pytest.approx(sum(b["strikeouts"] / b["plate_appearances"] for b in lineup) / 9)   # not the plain average


def test_lineup_with_too_few_usable_batters_is_refused_rather_than_guessed():
    assert model.summarize_lineup([batter(50, 250)] * 6) is None
    assert model.summarize_lineup([batter(50, 250)] * 6 + [None, None, None]) is None       # missing batters don't count
    assert model.summarize_lineup([batter(50, 250)] * 7 + [None, None]) is not None         # 7 is enough


def test_lineup_ignores_batters_with_no_plate_appearances_and_counts_small_samples():
    lineup = [batter(50, 250)] * 7 + [batter(0, 0), None, batter(3, 40)]
    s = model.summarize_lineup(lineup)
    assert s.n_batters == 8 and s.n_low_sample == 1                                            # 40 PA is under 100
    assert s.plate_appearances == 7 * 250 + 40
