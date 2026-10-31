"""Best value = price + time_weight * hours: a dearer but much shorter trip can beat the cheapest one."""
import asyncio

from flightchecker.discord_summary import format_trip_messages, limits_text, pick_value_trips
from flightchecker.models import RouteConfig
from flightchecker.scheduler import DailyRunner
from tests.conftest import make_result
from tests.test_discord_summary import pairing

ROUTE = RouteConfig(origin="BOM", destination="SFO", one_way=False,
                    outbound_window={"start": "2099-03-01", "end": "2099-03-01"},
                    return_window={"start": "2099-03-25", "end": "2099-03-25"},
                    max_stops=1, max_duration_hours=25.99, date_pairs=[("2099-03-01", "2099-03-25")])


def leg(leg_name: str, day: str, airline: str, price: float, duration: str):
    return make_result(origin="BOM", destination="SFO", leg=leg_name, depart_date=day, airline_text=airline,
                       price_text=f"${price:.0f}", duration_text=duration, stops_text="1 stop")


class FakeScraper:
    SOURCE = "google_flights"

    def __init__(self, cards: dict):
        self._cards = cards

    async def search(self, route, date_str, leg_name, run_date, cards):
        return self._cards.get((leg_name, date_str), []), []


def run_trip():
    cards = {
        ("outbound", "2099-03-01"): [leg("outbound", "2099-03-01", "SlowAir", 700, "25 hr"),
                                     leg("outbound", "2099-03-01", "FastAir", 760, "17 hr")],
        ("return", "2099-03-25"): [leg("return", "2099-03-25", "SlowAir", 700, "25 hr"),
                                   leg("return", "2099-03-25", "FastAir", 760, "17 hr")],
    }
    runner = DailyRunner([ROUTE], {"retries": {"max_attempts": 1}})
    return asyncio.run(runner._run_date_pairs(FakeScraper(cards), ROUTE, "google_flights", []))


def test_cheapest_trip_uses_the_cheaper_slow_flights():
    assert run_trip().best_pairings[0].total_price_usd == 1400


def test_best_value_trip_uses_the_dearer_fast_flights():
    assert run_trip().value_pairings[0].total_price_usd == 1520


def test_best_value_score_is_price_plus_fifteen_per_hour():
    assert run_trip().value_pairings[0].combined_score == 1520 + 15 * 34


def test_value_trips_skip_ones_already_in_the_cheapest_list():
    cheap = pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)
    cheap.combined_score = 300
    other = pairing("SFO", "BWI", "2026-11-16", "2026-11-19", 288)
    other.combined_score = 320
    assert pick_value_trips([cheap, other], shown=[cheap]) == [other]


def test_table_has_a_best_value_section_after_the_cheapest_rows():
    cheap = pairing("SJC", "DCA", "2026-12-02", "2026-12-05", 272)
    other = pairing("SFO", "BWI", "2026-11-16", "2026-11-19", 288)
    other.combined_score = 320
    table = format_trip_messages([cheap], "14:00", value_pairings=[other])[0]
    assert "-- best value: price + $15 per hour of flying --\n2  $288  $288  SFO-BWI" in table


def test_header_states_the_routes_own_limits():
    assert limits_text([ROUTE]) == "both legs max 1 stop and under 26 h"
