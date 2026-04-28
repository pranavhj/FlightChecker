import asyncio
import logging
from datetime import date

from playwright.async_api import async_playwright

from flightchecker.config_loader import date_range
from flightchecker.extraction.pipeline import ExtractionPipeline
from flightchecker.models import RouteConfig, RouteRunResult
from flightchecker.ranker import rank_results, combine_legs
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
        ua = browser_cfg.get("user_agent", "")

        all_results: list[RouteRunResult] = []

        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                slow_mo=slow_mo,
                user_agent=ua or None,
                accept_downloads=False,
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

        # Collect outbound results across all dates in window
        outbound_all = []
        out_dates = date_range(route.outbound_window)
        for d in out_dates:
            results, _ = await self._search_with_retry(scraper, route, d, "outbound", warnings)
            outbound_all.extend(results)

        outbound_ranked = rank_results(outbound_all, time_weight, self.top_n)
        outbound_processed = self._pipeline.process(outbound_ranked)

        return_ranked = []
        if not route.one_way and route.return_window:
            return_all = []
            ret_dates = date_range(route.return_window)
            for d in ret_dates:
                results, _ = await self._search_with_retry(scraper, route, d, "return", warnings)
                return_all.extend(results)
            return_ranked = rank_results(return_all, time_weight, self.top_n)
            return_ranked = self._pipeline.process(return_ranked)

        pairings = []
        if outbound_processed and return_ranked:
            pairings = combine_legs(outbound_processed, return_ranked, self.top_n)

        return RouteRunResult(
            route=route,
            source=source_name,
            outbound_results=outbound_processed,
            return_results=return_ranked,
            best_pairings=pairings,
            warnings=warnings,
        )

    async def _search_with_retry(self, scraper, route, date_str, leg, warnings):
        retry_cfg = self.settings.get("retries", {})
        max_attempts = retry_cfg.get("max_attempts", 3)
        backoff = retry_cfg.get("backoff_seconds", [30, 120, 300])

        for attempt in range(max_attempts):
            try:
                results, screenshots = await scraper.search(
                    route, date_str, leg, self.run_date, self.top_n
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
