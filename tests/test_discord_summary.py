from flightchecker.discord_summary import (
    DISCORD_LIMIT, airline_code, format_trip_messages, pick_trips, short_dates, short_duration,
    short_stops, short_time,
)
from flightchecker.models import LegPairing
from tests.conftest import make_result


def pairing(origin: str, dest: str, out_date: str, ret_date: str, total: float) -> LegPairing:
    out = make_result(origin=origin, destination=dest, leg="outbound", depart_date=out_date,
                      airline_text="Southwest", dep_time_text="6:00 AM\n–\n4:15 PM",
                      duration_text="7 hr 15 min", stops_text="1 stop",
                      search_url=f"https://www.google.com/travel/flights?q=out+{out_date}")
    ret = make_result(origin=origin, destination=dest, leg="return", depart_date=ret_date,
                      airline_text="Frontier", dep_time_text="9:35 PM", duration_text="8 hr",
                      stops_text="Nonstop", search_url=f"https://www.google.com/travel/flights?q=ret+{ret_date}")
    return LegPairing(outbound=out, ret=ret, total_price_usd=total, combined_score=total)


def test_known_airline_becomes_iata_code():
    assert airline_code("Southwest") == "WN"


def test_two_airlines_joined_with_plus():
    assert airline_code("Alaska, American") == "AS+AA"


def test_unknown_airline_truncated():
    assert airline_code("Condor Flugdienst") == "Condor"


def test_first_departure_time_taken_from_multiline_text():
    assert short_time("11:15 PM\n–\n9:35 AM") == "11:15p"


def test_time_with_google_narrow_no_break_space():
    assert short_time("6:30 PM\n\xa0–\xa0\n5:10 AM+1") == "6:30p"


def test_hours_only_duration_padded():
    assert short_duration("8 hr") == "8h00"


def test_hours_and_minutes_duration():
    assert short_duration("7 hr 15 min") == "7h15"


def test_nonstop_is_zero_stops():
    assert short_stops("Nonstop") == "0s"


def test_dates_in_same_month():
    assert short_dates("2026-12-02", "2026-12-05") == "Dec 2-5"


def test_dates_across_months():
    assert short_dates("2026-11-28", "2026-12-03") == "Nov 28-Dec 3"


def test_one_route_cannot_fill_the_table():
    pairs = [pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272),
             pairing("SJC", "DCA", "2026-12-03", "2026-12-06", 272),
             pairing("SJC", "DCA", "2026-12-04", "2026-12-07", 272),
             pairing("SFO", "BWI", "2026-11-16", "2026-11-23", 288)]
    assert [p.total_price_usd for p in pick_trips(pairs, per_route=2)] == [272, 272, 288]


def test_table_row_shows_route_dates_days_and_both_legs():
    table = format_trip_messages([pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)], "14:00")[0]
    assert "1  $272  $272  SJC-DCA Dec 2-5        3d  WN     6:00a 7h15 1s  F9     9:35p 8h00 0s" in table


def test_table_ranks_by_price_after_coupon():
    southwest = pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)
    southwest.coupon_usd, southwest.cost_usd = 100, 172
    other = pairing("SFO", "BWI", "2026-11-16", "2026-11-19", 200)
    other.cost_usd = 200
    assert [p.cost_usd for p in pick_trips([other, southwest])] == [172, 200]


def test_table_row_shows_pay_and_fare():
    p = pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)
    p.coupon_usd, p.cost_usd = 100, 172
    table = format_trip_messages([p], "14:00", {"airline": "Southwest", "amount_usd": 100})[0]
    assert "1  $172  $272  SJC-DCA" in table


def test_links_message_has_masked_out_and_back_links():
    links = format_trip_messages([pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)], "14:00")[1]
    assert links == ("1 [out](<https://www.google.com/travel/flights?q=out+2026-12-02>) · "
                     "[back](<https://www.google.com/travel/flights?q=ret+2026-12-05>)")


LONG_URL = "https://www.google.com/travel/flights?q=one+way+flights+from+SFO+to+BWI+November+16+2026"


def eight_trips_with_real_length_urls() -> list:
    pairs = [pairing(o, d, f"2026-12-{day:02d}", f"2026-12-{day + 4:02d}", 300 + day)
             for day in range(1, 5) for o, d in (("SJC", "DCA"), ("SFO", "IAD"), ("SFO", "BWI"), ("SJC", "IAD"))]
    for p in pairs:
        p.outbound.search_url = p.ret.search_url = LONG_URL
    return pairs


def test_eight_trips_post_as_table_plus_one_links_message():
    assert len(format_trip_messages(eight_trips_with_real_length_urls(), "14:00")) == 2


def test_every_message_fits_discord_limit():
    assert max(len(m) for m in format_trip_messages(eight_trips_with_real_length_urls(), "14:00")) <= DISCORD_LIMIT


def test_no_trips_gives_single_short_message():
    assert format_trip_messages([], "14:00") == ["**FlightChecker** (14:00 UTC): no trip passed the filters."]
