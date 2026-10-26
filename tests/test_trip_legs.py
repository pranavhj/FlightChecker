"""Both legs of a date-pair trip are filtered on their own: max stops and max duration."""
import asyncio

from flightchecker.models import RouteConfig
from flightchecker.scheduler import DailyRunner
from tests.conftest import make_result


class FakeScraper:
    SOURCE = "google_flights"

    def __init__(self, cards: dict):
        self._cards = cards  # {(leg, date): [FlightResult, ...]}

    async def search(self, route, date_str, leg, run_date, cards):
        return self._cards.get((leg, date_str), []), []


def card(leg: str, date: str, price: str, duration: str, stops: str):
    return make_result(origin="SJC", destination="DCA", leg=leg, depart_date=date,
                       price_text=price, duration_text=duration, stops_text=stops)


ROUTE = RouteConfig(origin="SJC", destination="DCA", one_way=False,
                    outbound_window={"start": "2099-03-01", "end": "2099-03-01"},
                    return_window={"start": "2099-03-04", "end": "2099-03-04"},
                    max_stops=1, max_duration_hours=8.49,
                    date_pairs=[("2099-03-01", "2099-03-04")])

GOOD_OUT = card("outbound", "2099-03-01", "$150", "7 hr 15 min", "1 stop")


def run_pairs(return_cards: list) -> list:
    scraper = FakeScraper({("outbound", "2099-03-01"): [GOOD_OUT], ("return", "2099-03-04"): return_cards})
    runner = DailyRunner([ROUTE], {"retries": {"max_attempts": 1}})
    result = asyncio.run(runner._run_date_pairs(scraper, ROUTE, "google_flights", []))
    return [p.total_price_usd for p in result.best_pairings]


def test_trip_dropped_when_only_return_has_two_stops():
    assert run_pairs([card("return", "2099-03-04", "$99", "6 hr", "2 stops")]) == []


def test_trip_dropped_when_return_takes_eight_and_a_half_hours():
    assert run_pairs([card("return", "2099-03-04", "$99", "8 hr 30 min", "1 stop")]) == []


def test_return_just_under_eight_and_a_half_hours_qualifies():
    assert run_pairs([card("return", "2099-03-04", "$99", "8 hr 29 min", "1 stop")]) == [249.0]


def test_cheapest_qualifying_return_chosen_over_cheaper_two_stop_fare():
    assert run_pairs([card("return", "2099-03-04", "$80", "7 hr", "2 stops"),
                      card("return", "2099-03-04", "$120", "7 hr", "1 stop")]) == [270.0]


def test_return_with_unreadable_stops_is_rejected():
    assert run_pairs([card("return", "2099-03-04", "$99", "7 hr", "")]) == []
