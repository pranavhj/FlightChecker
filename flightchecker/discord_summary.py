"""Compact Discord summary for date-pair trips: one monospace table, then one line of links.

Discord does not render Markdown tables, so the table goes in a code block; links can't be
clicked inside a code block, so they follow as short masked links ([1 out](<url>) ...).
"""
from __future__ import annotations

import re
from datetime import date

DISCORD_LIMIT = 2000

_AIRLINE_CODES = {
    "alaska": "AS", "american": "AA", "breeze": "MX", "delta": "DL", "frontier": "F9",
    "hawaiian": "HA", "jetblue": "B6", "southwest": "WN", "spirit": "NK", "sun country": "SY",
    "united": "UA",
    # long-haul (Mumbai <-> SF searches)
    "air france": "AF", "air india": "AI", "all nippon": "NH", "ana": "NH", "asiana": "OZ",
    "british": "BA", "cathay": "CX", "china airlines": "CI", "emirates": "EK", "etihad": "EY",
    "eva": "BR", "finnair": "AY", "indigo": "6E", "japan": "JL", "klm": "KL", "korean": "KE",
    "lufthansa": "LH", "qatar": "QR", "singapore": "SQ", "swiss": "LX", "thai": "TG",
    "turkish": "TK", "virgin atlantic": "VS", "vistara": "UK",
}


def airline_code(text: str) -> str:
    """'Southwest' -> 'WN', 'Alaska, American' -> 'AS+AA', unknown -> first 6 chars."""
    if not text:
        return "?"
    codes = []
    for name in re.split(r",|·|\band\b", text):
        name = name.strip().lower()
        if name:
            codes.append(next((c for k, c in _AIRLINE_CODES.items() if name.startswith(k)), name[:6].title()))
    return "+".join(codes)


def short_time(text: str) -> str:
    """First clock time in scraped text: '11:15 PM\\n–\\n9:35 AM' -> '11:15p'."""
    m = re.search(r"(\d{1,2}:\d{2})\s*([AP])M", text or "", re.I)
    return f"{m.group(1)}{m.group(2).lower()}" if m else "?"


def short_duration(text: str) -> str:
    """'7 hr 15 min' -> '7h15', '8 hr' -> '8h00'."""
    m = re.search(r"(\d+)\s*h(?:r|our)?s?(?:\s*(\d+)\s*m)?", text or "", re.I)
    return f"{m.group(1)}h{int(m.group(2) or 0):02d}" if m else "?"


def short_stops(text: str) -> str:
    """'Nonstop' -> '0s', '1 stop' -> '1s'."""
    if "nonstop" in (text or "").lower():
        return "0s"
    m = re.search(r"(\d+)\s*stop", text or "", re.I)
    return f"{m.group(1)}s" if m else "?"


def short_dates(out_iso: str, ret_iso: str) -> str:
    """'2026-12-02','2026-12-05' -> 'Dec 2-5'; across months -> 'Nov 28-Dec 3'."""
    out, ret = date.fromisoformat(out_iso), date.fromisoformat(ret_iso)
    if out.month == ret.month:
        return f"{out:%b} {out.day}-{ret.day}"
    return f"{out:%b} {out.day}-{ret:%b} {ret.day}"


def _leg(r) -> str:
    return f"{airline_code(r.airline_text):<5} {short_time(r.dep_time_text):>6} {short_duration(r.duration_text)} {short_stops(r.stops_text)}"


def pick_trips(pairings: list, max_rows: int = 8, per_route: int | None = None) -> list:
    """Cheapest trips overall, at most `per_route` per origin->destination so one route can't fill the table.

    Default per_route splits the rows evenly over the routes present (min 2): one route gets all 8 rows.
    """
    if per_route is None:
        routes = {(p.outbound.origin, p.outbound.destination) for p in pairings}
        per_route = max(2, -(-max_rows // max(len(routes), 1)))
    picked, count = [], {}
    for p in sorted(pairings, key=lambda p: (_cost(p), p.total_price_usd)):
        key = (p.outbound.origin, p.outbound.destination)
        if count.get(key, 0) < per_route:
            picked.append(p)
            count[key] = count.get(key, 0) + 1
        if len(picked) == max_rows:
            break
    return picked


def _cost(p) -> float:
    """What you pay for the trip: after the coupon when one applies."""
    return p.cost_usd if p.cost_usd is not None else p.total_price_usd


def limits_text(routes: list) -> str:
    """'both legs max 1 stop and under 26 h' from the routes' max_stops / max_duration_hours."""
    stops = [r.max_stops for r in routes if r.max_stops is not None]
    hours = [r.max_duration_hours for r in routes if r.max_duration_hours is not None]
    parts = []
    if stops:
        parts.append(f"max {max(stops)} stop" + ("" if max(stops) == 1 else "s"))
    if hours:
        parts.append(f"under {round(max(hours) * 2) / 2:g} h")
    return "both legs " + " and ".join(parts) if parts else "both legs checked"


def format_trip_messages(pairings: list, run_time: str, coupon: dict | None = None,
                         limits: str = "both legs max 1 stop and under 8.5 h") -> list[str]:
    """Discord messages (each <= 2000 chars): header + table, then links (8 rows of links fit one message)."""
    trips = pick_trips(pairings)
    if not trips:
        return [f"**FlightChecker** ({run_time} UTC): no trip passed the filters."]
    header = f"{'#':<2} {'Pay':<5} {'Fare':<5} {'Route':<7} {'Dates':<12} {'Days':>4}  {'Out':<20}  Back"
    rows = []
    for i, p in enumerate(trips, 1):
        out, ret = p.outbound, p.ret
        days = (date.fromisoformat(ret.depart_date) - date.fromisoformat(out.depart_date)).days
        rows.append(f"{i:<2} {f'${_cost(p):.0f}':<5} {f'${p.total_price_usd:.0f}':<5} {out.origin}-{out.destination} "
                    f"{short_dates(out.depart_date, ret.depart_date):<12} {days:>3}d  {_leg(out)}  {_leg(ret)}")
    credit = (f"Pay = fare minus your ${coupon['amount_usd']} {coupon['airline']} credit (once per trip); "
              if coupon else "")
    table = (f"**FlightChecker** ({run_time} UTC): cheapest trips, {limits}\n"
             "```\n" + "\n".join([header, *rows]) + "\n```\n"
             f"-# {credit}Out/Back = airline, departs, duration, stops (0s = nonstop)")
    links = [f"{i} [out](<{p.outbound.search_url}>) · [back](<{p.ret.search_url}>)" for i, p in enumerate(trips, 1)]
    return [table, *_chunk(links, "\n")]


def _chunk(parts: list[str], sep: str) -> list[str]:
    """Join parts with sep into as few messages as fit under the Discord limit."""
    messages, current = [], ""
    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) > DISCORD_LIMIT:
            messages.append(current)
            candidate = part
        current = candidate
    if current:
        messages.append(current)
    return messages
