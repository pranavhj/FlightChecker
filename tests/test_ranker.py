import pytest
from flightchecker.ranker import parse_price, parse_hours, compute_score, rank_results, combine_legs
from tests.conftest import make_result


def test_parse_price_basic():
    assert parse_price("$189") == 189.0


def test_parse_price_comma():
    assert parse_price("$1,234") == 1234.0


def test_parse_price_no_symbol():
    assert parse_price("189") == 189.0


def test_parse_price_invalid():
    assert parse_price("N/A") is None


def test_parse_hours_full():
    assert parse_hours("2h 30m") == pytest.approx(2.5)


def test_parse_hours_no_minutes():
    assert parse_hours("3h") == 3.0


def test_parse_hours_invalid():
    assert parse_hours("nonstop") is None


def test_compute_score():
    assert compute_score(200.0, 2.0, 15.0) == pytest.approx(230.0)


def test_compute_score_none_inputs():
    assert compute_score(None, 2.0, 15.0) is None
    assert compute_score(200.0, None, 15.0) is None


def test_rank_results_sorted_ascending():
    r1 = make_result(price_text="$250", duration_text="3h 0m")   # score = 250 + 45 = 295
    r2 = make_result(price_text="$189", duration_text="1h 30m")  # score = 189 + 22.5 = 211.5
    r3 = make_result(price_text="$300", duration_text="1h 0m")   # score = 300 + 15 = 315
    ranked = rank_results([r1, r2, r3], time_weight=15.0, top_n=3)
    assert ranked[0].price_usd == 189.0
    assert ranked[1].price_usd == 250.0
    assert ranked[2].price_usd == 300.0


def test_rank_results_top_n():
    results = [make_result(price_text=f"${100 + i*10}", duration_text="1h 0m") for i in range(5)]
    ranked = rank_results(results, time_weight=15.0, top_n=3)
    assert len(ranked) == 3


def test_combine_legs_sorts_by_combined_score():
    out1 = make_result(price_text="$79", duration_text="1h 30m", leg="outbound")
    out2 = make_result(price_text="$120", duration_text="1h 30m", leg="outbound")
    ret1 = make_result(price_text="$89", duration_text="1h 25m", leg="return")

    # Pre-rank to compute scores
    from flightchecker.ranker import rank_results
    [out1, out2] = rank_results([out1, out2], 15.0, 2)
    [ret1] = rank_results([ret1], 15.0, 1)

    pairings = combine_legs([out1, out2], [ret1], top_n=2)
    assert len(pairings) == 2
    assert pairings[0].total_price_usd < pairings[1].total_price_usd
