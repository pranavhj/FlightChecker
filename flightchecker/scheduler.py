import asyncio
import logging
import os
import sys
from datetime import date

from playwright.async_api import async_playwright

from flightchecker.config_loader import date_range
from flightchecker.extraction.pipeline import ExtractionPipeline
from flightchecker.models import LegPairing, RouteConfig, RouteRunResult
from flightchecker.ranker import (
    rank_results, combine_legs, coupon_discount, has_checked_bag, is_coupon_airline, is_single_airline,
    parse_hours, parse_price, parse_stops,
)
from flightchecker.scrapers.google_flights import GoogleFlightsScraper
from flightchecker.scrapers.skyscanner import SkyscannerScraper

logger = logging.getLogger(__name__)

_SCRAPER_MAP = {
    "google_flights": GoogleFlightsScraper,
    "skyscanner": SkyscannerScraper,
}


class DailyRunner:
    def __init__(self, routes: list[RouteConfig], settings: dict, top_n: int = 3):
        self.routes = routes
        self.settings = settings
        self.top_n = top_n
        self.run_date = date.today().isoformat()
        self._pipeline = ExtractionPipeline(settings)

    async def run(self) -> list[RouteRunResult]:
        browser_cfg = self.settings.get("browser", {})
        profile_dir = browser_cfg.get("persistent_context_dir", ".browser_profile")
        headless = browser_cfg.get("headless", True)
        slow_mo = browser_cfg.get("slow_mo_ms", 150)
        # Linux (the Pi): Debian chromium (Playwright has no build for it) and a matching Linux UA
        on_linux = sys.platform.startswith("linux")
        ua = browser_cfg.get("user_agent_linux" if on_linux else "user_agent", "")
        executable = os.getenv("FLIGHTCHECKER_CHROMIUM") or (browser_cfg.get("executable_path_linux") if on_linux else None)

        all_results: list[RouteRunResult] = []

        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(
                profile_dir,
                executable_path=executable or None,
                headless=headless,
                slow_mo=slow_mo,
                user_agent=ua or None,
                accept_downloads=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            # Mask navigator.webdriver to avoid bot detection
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            for route in self.routes:
                sources = self.settings.get("sources", ["google_flights"])
                for source_name in sources:
                    result = await self._run_route_source(context, route, source_name)
                    all_results.append(result)

            await context.close()

        return all_results

    async def _run_route_source(
        self, context, route: RouteConfig, source_name: str
    ) -> RouteRunResult:
        scraper_cls = _SCRAPER_MAP.get(source_name)
        if scraper_cls is None:
            logger.error("Unknown source: %s", source_name)
            return RouteRunResult(route=route, source=source_name, warnings=[f"Unknown source: {source_name}"])

        scraper = scraper_cls(context, self.settings)
        time_weight = self.settings.get("scoring", {}).get("time_weight_usd_per_hour", 15.0)
        warnings: list[str] = []

        if route.date_pairs:
            return await self._run_date_pairs(scraper, route, source_name, warnings)

        # Collect outbound results across all dates in window
        outbound_all = []
        out_dates = date_range(route.outbound_window)
        logger.info("Starting %s->%s via %s: %d outbound dates",
                    route.origin, route.destination, source_name, len(out_dates))
        for d in out_dates:
            results, _ = await self._search_with_retry(scraper, route, d, "outbound", warnings)
            outbound_all.extend(results)

        outbound_ranked = rank_results(outbound_all, time_weight, self.top_n)
        outbound_processed = self._pipeline.process(outbound_ranked)

        # Apply nonstop filter if requested
        if route.nonstop_only:
            outbound_processed = [
                r for r in outbound_processed
                if r.stops_text and "nonstop" in r.stops_text.lower()
            ]

        # Apply max duration filter
        if route.max_duration_hours is not None:
            outbound_processed = [
                r for r in outbound_processed
                if r.total_hours is None or r.total_hours <= route.max_duration_hours
            ]

        # Apply checked bag filter
        if route.checked_bag_required:
            outbound_processed = [
                r for r in outbound_processed
                if has_checked_bag(r.baggage_text)
            ]

        # Apply same-airline filter
        if route.same_airline_only:
            outbound_processed = [
                r for r in outbound_processed
                if is_single_airline(r.airline_text)
            ]

        return_ranked = []
        return_all = []
        if not route.one_way and route.return_window:
            ret_dates = date_range(route.return_window)
            for d in ret_dates:
                results, _ = await self._search_with_retry(scraper, route, d, "return", warnings)
                return_all.extend(results)
            return_ranked = rank_results(return_all, time_weight, self.top_n)
            return_ranked = self._pipeline.process(return_ranked)

            # Apply nonstop filter if requested
            if route.nonstop_only:
                return_ranked = [
                    r for r in return_ranked
                    if r.stops_text and "nonstop" in r.stops_text.lower()
                ]

            # Apply max duration filter
            if route.max_duration_hours is not None:
                return_ranked = [
                    r for r in return_ranked
                    if r.total_hours is None or r.total_hours <= route.max_duration_hours
                ]

            # Apply checked bag filter
            if route.checked_bag_required:
                return_ranked = [
                    r for r in return_ranked
                    if has_checked_bag(r.baggage_text)
                ]

            # Apply same-airline filter
            if route.same_airline_only:
                return_ranked = [
                    r for r in return_ranked
                    if is_single_airline(r.airline_text)
                ]

        pairings = []
        if outbound_processed and return_ranked:
            pairings = combine_legs(
                outbound_processed,
                return_ranked,
                self.top_n,
                nonstop_only=route.nonstop_only,
                same_day_return=route.same_day_return,
            )

        # Round-trip sweep: top-5 outbound dates × top-5 return dates (up to 25 searches)
        roundtrip_results = []
        if not route.one_way and route.return_window and outbound_all and return_all and hasattr(scraper, "search_roundtrip"):
            # Parse prices into all raw results so we can rank by date
            for r in outbound_all:
                if r.price_usd is None:
                    r.price_usd = parse_price(r.price_text)
            for r in return_all:
                if r.price_usd is None:
                    r.price_usd = parse_price(r.price_text)

            out_by_date: dict[str, float] = {}
            for r in outbound_all:
                if r.price_usd is not None:
                    if r.depart_date not in out_by_date or r.price_usd < out_by_date[r.depart_date]:
                        out_by_date[r.depart_date] = r.price_usd
            top_out_dates = sorted(out_by_date, key=out_by_date.get)[:5]

            ret_by_date: dict[str, float] = {}
            for r in return_all:
                if r.price_usd is not None:
                    if r.depart_date not in ret_by_date or r.price_usd < ret_by_date[r.depart_date]:
                        ret_by_date[r.depart_date] = r.price_usd
            top_ret_dates = sorted(ret_by_date, key=ret_by_date.get)[:5]

            logger.info(
                "Round-trip sweep: %d out × %d ret = %d combos",
                len(top_out_dates), len(top_ret_dates), len(top_out_dates) * len(top_ret_dates),
            )
            for out_date in top_out_dates:
                for ret_date in top_ret_dates:
                    rt_batch, _ = await self._search_roundtrip_with_retry(
                        scraper, route, out_date, ret_date, warnings
                    )
                    roundtrip_results.extend(rt_batch)

            for r in roundtrip_results:
                if r.price_usd is None:
                    r.price_usd = parse_price(r.price_text)
                if r.total_hours is None:
                    from flightchecker.ranker import parse_hours
                    r.total_hours = parse_hours(r.duration_text)
            # Apply max duration filter to round-trip results (duration_text holds the longer leg)
            if route.max_duration_hours is not None:
                roundtrip_results = [
                    r for r in roundtrip_results
                    if r.total_hours is None or r.total_hours <= route.max_duration_hours
                ]
            roundtrip_results.sort(key=lambda r: r.price_usd if r.price_usd is not None else float("inf"))
            roundtrip_results = roundtrip_results[: self.top_n * 3]

        return RouteRunResult(
            route=route,
            source=source_name,
            outbound_results=outbound_processed,
            return_results=return_ranked,
            best_pairings=pairings,
            roundtrip_results=roundtrip_results,
            warnings=warnings,
        )

    async def _run_date_pairs(self, scraper, route, source_name, warnings) -> RouteRunResult:
        """Weekend trips: search each leg one-way, filter BOTH legs, pair by date, cheapest total first.

        A round-trip results page only describes the outbound flight, so the return leg's
        stops and duration can't be verified there. Each leg is searched and filtered on its own.
        """
        time_weight = self.settings.get("scoring", {}).get("time_weight_usd_per_hour", 15.0)
        out_dates = sorted({p[0] for p in route.date_pairs})
        ret_dates = sorted({p[1] for p in route.date_pairs})
        logger.info("Starting %s->%s via %s: %d outbound + %d return one-way searches (max_stops=%s, max_hours=%s)",
                    route.origin, route.destination, source_name, len(out_dates), len(ret_dates),
                    route.max_stops, route.max_duration_hours)

        coupon = self.settings.get("coupon")
        best_out = await self._cheapest_leg_per_date(scraper, route, out_dates, "outbound", warnings, coupon, time_weight)
        best_ret = await self._cheapest_leg_per_date(scraper, route, ret_dates, "return", warnings, coupon, time_weight)

        pairings, value_pairings = [], []
        for out_date, ret_date in route.date_pairs:
            outs, rets = best_out.get(out_date, []), best_ret.get(ret_date, [])
            if not outs or not rets:
                logger.info("%s->%s %s/%s: no qualifying %s leg", route.origin, route.destination,
                            out_date, ret_date, "outbound" if not outs else "return")
                continue
            # Cheapest leg vs cheapest coupon-airline leg per date: keep the combination you pay least for
            options = []
            for out in outs:
                for ret in rets:
                    total = out.price_usd + ret.price_usd
                    discount = coupon_discount(out, ret, coupon)
                    options.append(LegPairing(
                        outbound=out, ret=ret, total_price_usd=total,
                        combined_score=round(total - discount + time_weight * (out.total_hours + ret.total_hours), 2),
                        coupon_usd=discount, cost_usd=total - discount,
                    ))
            pairings.append(min(options, key=lambda p: (p.cost_usd, p.combined_score)))
            value_pairings.append(min(options, key=lambda p: (p.combined_score, p.cost_usd)))
        pairings.sort(key=lambda p: (p.cost_usd, p.combined_score))
        value_pairings.sort(key=lambda p: (p.combined_score, p.cost_usd))
        logger.info("%s->%s: %d of %d date pairs have a qualifying trip", route.origin, route.destination,
                    len(pairings), len(route.date_pairs))
        return RouteRunResult(
            route=route, source=source_name,
            outbound_results=sorted((r for legs in best_out.values() for r in legs), key=lambda r: r.price_usd),
            return_results=sorted((r for legs in best_ret.values() for r in legs), key=lambda r: r.price_usd),
            best_pairings=pairings, value_pairings=value_pairings, warnings=warnings,
        )

    async def _cheapest_leg_per_date(self, scraper, route, dates, leg, warnings, coupon: dict | None = None,
                                     time_weight: float = 15.0) -> dict:
        """One-way search per date; return {date: [cheapest qualifying leg, best-value leg, cheapest coupon-airline leg]}.

        Best value = lowest price + time_weight * hours. It and the coupon-airline leg are kept even
        when dearer (a shorter flight, or the credit, can make the trip the better deal); entries
        that coincide with an earlier one are left out, so the list has 1-3 legs.
        Legs whose price, stops or duration can't be read are rejected, not passed through.
        """
        best = {}
        for d in dates:
            # Google sorts by "Best", not price: read several cards and pick the cheapest that qualifies
            cards, _ = await self._search_with_retry(scraper, route, d, leg, warnings, cards=10)
            ok = []
            for r in cards:
                r.price_usd = r.price_usd if r.price_usd is not None else parse_price(r.price_text)
                r.total_hours = r.total_hours if r.total_hours is not None else parse_hours(r.duration_text)
                stops = parse_stops(r.stops_text)
                if r.price_usd is None or r.total_hours is None or stops is None:
                    continue
                if route.nonstop_only and stops != 0:
                    continue
                if route.max_stops is not None and stops > route.max_stops:
                    continue
                if route.max_duration_hours is not None and r.total_hours > route.max_duration_hours:
                    continue
                ok.append(r)
            logger.debug("%s %s %s: %d cards, %d qualify", route.origin, leg, d, len(cards), len(ok))
            if cards and not ok:
                logger.info("%s->%s %s %s: %d cards read, none qualify", route.origin, route.destination, leg, d, len(cards))
            if ok:
                cheapest = min(ok, key=lambda r: r.price_usd)
                best[d] = [cheapest]
                # Best value = price + time_weight * hours: may be dearer than the cheapest but much shorter
                value = min(ok, key=lambda r: r.price_usd + time_weight * r.total_hours)
                if value is not cheapest:
                    best[d].append(value)
                coupon_legs = [r for r in ok if is_coupon_airline(r, coupon)]
                if coupon_legs and not any(is_coupon_airline(r, coupon) for r in best[d]):
                    best[d].append(min(coupon_legs, key=lambda r: r.price_usd))
        return best

    async def _search_with_retry(self, scraper, route, date_str, leg, warnings, cards: int | None = None):
        retry_cfg = self.settings.get("retries", {})
        max_attempts = retry_cfg.get("max_attempts", 3)
        backoff = retry_cfg.get("backoff_seconds", [30, 120, 300])

        for attempt in range(max_attempts):
            try:
                results, screenshots = await scraper.search(
                    route, date_str, leg, self.run_date, cards or self.top_n
                )
                return results, screenshots
            except Exception as e:
                wait = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                msg = f"[{scraper.SOURCE}/{route.origin}→{route.destination}/{leg}/{date_str}] attempt {attempt+1} failed: {e}. Retrying in {wait}s."
                logger.warning(msg)
                warnings.append(msg)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait)

        return [], []

    async def _search_roundtrip_with_retry(self, scraper, route, out_date, ret_date, warnings, cards: int = 1):
        retry_cfg = self.settings.get("retries", {})
        max_attempts = retry_cfg.get("max_attempts", 3)
        backoff = retry_cfg.get("backoff_seconds", [30, 120, 300])

        for attempt in range(max_attempts):
            try:
                results, screenshots = await scraper.search_roundtrip(
                    route, out_date, ret_date, self.run_date, cards
                )
                return results, screenshots
            except Exception as e:
                wait = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                msg = f"[RT/{route.origin}→{route.destination}/{out_date}/{ret_date}] attempt {attempt+1} failed: {e}. Retrying in {wait}s."
                logger.warning(msg)
                warnings.append(msg)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait)

        return [], []
