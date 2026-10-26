import re
from typing import Optional

from flightchecker.models import FlightResult, LegPairing

PRICE_RE = re.compile(r"[\$]?([\d,]+)")
DURATION_RE = re.compile(r"(\d+)h\s*(\d*)m?")


def parse_price(text: str) -> Optional[float]:
    m = PRICE_RE.search(text.replace(",", ""))
    if m:
        return float(m.group(1))
    return None


def parse_hours(text: str) -> Optional[float]:
    m = DURATION_RE.search(text)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else 0
        return round(hours + minutes / 60, 4)
    return None


def compute_score(price_usd: Optional[float], total_hours: Optional[float], time_weight: float) -> Optional[float]:
    if price_usd is None or total_hours is None:
        return None
    return round(price_usd + time_weight * total_hours, 2)


def rank_results(results: list[FlightResult], time_weight: float, top_n: int) -> list[FlightResult]:
    for r in results:
        if r.price_usd is None:
            r.price_usd = parse_price(r.price_text)
        if r.total_hours is None:
            r.total_hours = parse_hours(r.duration_text)
        r.score = compute_score(r.price_usd, r.total_hours, time_weight)

    scored = [r for r in results if r.score is not None]
    unscored = [r for r in results if r.score is None]
    scored.sort(key=lambda r: r.score)
    return (scored + unscored)[:top_n]


def combine_legs(
    outbound: list[FlightResult],
    returns: list[FlightResult],
    top_n: int,
    nonstop_only: bool = False,
    same_day_return: bool = False,
) -> list[LegPairing]:
    """Cartesian product of outbound × return legs ranked by combined score."""
    pairings = []
    for o in outbound:
        # Apply nonstop filter for outbound
        if nonstop_only and o.stops_text and "nonstop" not in o.stops_text.lower():
            continue

        for r in returns:
            # Apply nonstop filter for return
            if nonstop_only and r.stops_text and "nonstop" not in r.stops_text.lower():
                continue

            # Apply same-day return filter
            if same_day_return and o.depart_date != r.depart_date:
                continue

            if o.price_usd is None or r.price_usd is None:
                continue
            total_price = o.price_usd + r.price_usd
            if o.score is not None and r.score is not None:
                combined = round(o.score + r.score, 2)
            else:
                combined = total_price
            pairings.append(LegPairing(
                outbound=o,
                ret=r,
                total_price_usd=total_price,
                combined_score=combined,
            ))
    pairings.sort(key=lambda p: p.combined_score)
    return pairings[:top_n]
