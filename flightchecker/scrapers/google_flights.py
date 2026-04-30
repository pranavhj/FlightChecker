import logging
from datetime import date as dobj
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext

from flightchecker.models import FlightResult, RouteConfig
from flightchecker.scrapers.base_scraper import BaseScraper
from flightchecker.scrapers.selector_registry import SELECTORS
from flightchecker.utils.screenshot import screenshot_path

logger = logging.getLogger(__name__)

_S = SELECTORS["google_flights"]


class GoogleFlightsScraper(BaseScraper):
    SOURCE = "google_flights"

    def __init__(self, context: BrowserContext, settings: dict):
        super().__init__(context, settings)

    def _build_url(self, origin: str, destination: str, date: str) -> str:
        d = dobj.fromisoformat(date)
        # Natural-language query: Google Flights interprets this and shows results directly
        q = f"one way flights from {origin} to {destination} {d.strftime('%B')} {d.day} {d.year}"
        return f"https://www.google.com/travel/flights?q={quote_plus(q)}"

    async def search(
        self,
        route: RouteConfig,
        depart_date: str,
        leg: str,
        run_date: str,
        top_n: int,
    ) -> tuple[list[FlightResult], list[str]]:
        """
        Search one leg (outbound or return) as a one-way flight.
        Returns (results, screenshot_paths).
        """
        if leg == "return":
            origin, destination = route.destination, route.origin
        else:
            origin, destination = route.origin, route.destination

        url = self._build_url(origin, destination, depart_date)
        page = await self.new_page()
        screenshots: list[str] = []
        raw_rows: list[dict] = []

        try:
            logger.info("GoogleFlights navigating to: %s", url)
            await page.goto(url, wait_until="commit", timeout=15_000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=12_000)
            except Exception:
                pass
            await self.human_pause(2000, 3500)

            # Wait for flight result cards to appear
            try:
                await page.wait_for_selector(_S["card"][0], timeout=15_000)
            except Exception:
                logger.warning("GoogleFlights: timed out waiting for result cards")

            await self.scroll_into_results(page)
            await self.human_pause(800, 1500)

            ss_path = screenshot_path(
                self._screenshots_dir, run_date, self.SOURCE,
                origin, destination, depart_date, leg, "results"
            )
            shot = await self.safe_screenshot(page, ss_path)
            if shot:
                screenshots.append(shot)

            raw_rows = await self._extract_cards(page, origin, destination, depart_date, leg, top_n, shot)

        except Exception as e:
            logger.error("GoogleFlights search failed [%s->%s %s %s]: %s", origin, destination, depart_date, leg, e)
        finally:
            await page.close()

        return raw_rows, screenshots

    async def _extract_cards(
        self,
        page,
        origin: str,
        destination: str,
        date: str,
        leg: str,
        top_n: int,
        screenshot: str,
    ) -> list[FlightResult]:
        cards = await self.try_selectors(page, _S["card"])
        results = []
        for card in cards[:top_n]:
            price_text = await self.get_text(card, _S["price"])
            airline_text = await self.get_text(card, _S["airline"])
            duration_text = await self.get_text(card, _S["duration"])
            stops_text = await self.get_text(card, _S["stops"])
            dep_time_text = await self.get_text(card, _S["dep_time"])
            arr_time_text = await self.get_text(card, _S["arr_time"])

            all_present = all([price_text, airline_text, duration_text, dep_time_text])
            confidence = "high" if all_present else "low"
            method = "dom" if all_present else "manual_review"

            results.append(FlightResult(
                source=self.SOURCE,
                origin=origin,
                destination=destination,
                depart_date=date,
                leg=leg,
                price_text=price_text,
                duration_text=duration_text,
                stops_text=stops_text,
                airline_text=airline_text,
                dep_time_text=dep_time_text,
                arr_time_text=arr_time_text,
                confidence=confidence,
                screenshot_path=screenshot,
                extraction_method=method,
            ))
        return results
