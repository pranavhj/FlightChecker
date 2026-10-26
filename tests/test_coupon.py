"""The single-use Southwest credit: how much it takes off, and which trip wins once it's applied."""
import asyncio

from flightchecker.models import RouteConfig
from flightchecker.ranker import coupon_discount
from flightchecker.scheduler import DailyRunner
from tests.conftest import make_result

SW_COUPON = {"airline": "Southwest", "amount_usd": 100}


def leg(airline: str, price: float, leg_name: str = "outbound", day: str = "2099-03-01"):
    r = make_result(origin="SJC", destination="DCA", leg=leg_name, depart_date=day, airline_text=airline,
                    price_text=f"${price:.0f}", duration_text="7 hr", stops_text="1 stop")
    r.price_usd = price
    return r


def test_coupon_applied_once_when_both_legs_southwest():
    assert coupon_discount(leg("Southwest", 136), leg("Southwest", 136), SW_COUPON) == 100


def test_coupon_capped_at_southwest_fare():
    assert coupon_discount(leg("Southwest", 60), leg("Delta", 150), SW_COUPON) == 60


def test_no_coupon_on_non_southwest_trip():
    assert coupon_discount(leg("Delta", 136), leg("United", 136), SW_COUPON) == 0


def test_no_discount_without_coupon_setting():
    assert coupon_discount(leg("Southwest", 136), leg("Southwest", 136), None) == 0


class FakeScraper:
    SOURCE = "google_flights"

    def __init__(self, cards: dict):
        self._cards = cards

    async def search(self, route, date_str, leg_name, run_date, cards):
        return self._cards.get((leg_name, date_str), []), []


ROUTE = RouteConfig(origin="SJC", destination="DCA", one_way=False,
                    outbound_window={"start": "2099-03-01", "end": "2099-03-01"},
                    return_window={"start": "2099-03-04", "end": "2099-03-04"},
                    max_stops=1, max_duration_hours=8.49, date_pairs=[("2099-03-01", "2099-03-04")])


def best_trip(out_cards: list, ret_cards: list, coupon: dict | None):
    scraper = FakeScraper({("outbound", "2099-03-01"): out_cards, ("return", "2099-03-04"): ret_cards})
    settings = {"retries": {"max_attempts": 1}, "coupon": coupon}
    result = asyncio.run(DailyRunner([ROUTE], settings)._run_date_pairs(scraper, ROUTE, "google_flights", []))
    p = result.best_pairings[0]
    return p.outbound.airline_text, p.ret.airline_text, p.total_price_usd, p.cost_usd


def test_dearer_southwest_leg_wins_once_credit_applied():
    outs = [leg("Delta", 120), leg("Southwest", 150)]
    rets = [leg("Delta", 100, "return", "2099-03-04"), leg("Southwest", 140, "return", "2099-03-04")]
    assert best_trip(outs, rets, SW_COUPON) == ("Southwest", "Delta", 250, 150)


def test_other_airline_wins_only_when_cheaper_than_southwest_after_credit():
    outs = [leg("Delta", 50), leg("Southwest", 150)]
    rets = [leg("Delta", 50, "return", "2099-03-04"), leg("Southwest", 150, "return", "2099-03-04")]
    assert best_trip(outs, rets, SW_COUPON) == ("Delta", "Delta", 100, 100)


def test_without_coupon_cheapest_fare_wins():
    outs = [leg("Delta", 120), leg("Southwest", 150)]
    rets = [leg("Delta", 100, "return", "2099-03-04"), leg("Southwest", 140, "return", "2099-03-04")]
    assert best_trip(outs, rets, None) == ("Delta", "Delta", 220, 220)
