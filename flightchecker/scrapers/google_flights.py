import logging
from pathlib import Path

from playwright.async_api import BrowserContext

from flightchecker.models import FlightResult, RouteConfig
from flightchecker.scrapers.base_scraper import BaseScraper
from flightchecker.scrapers.selector_registry import SELECTORS
from flightchecker.utils.screenshot import screenshot_path

logger = logging.getLogger(__name__)

_S = SELECTORS["google_flights"]
_BASE_URL = "https://www.google.com/travel/flights"


class GoogleFlightsScraper(BaseScraper):
    SOURCE = "google_flights"

    def __init__(self, context: BrowserContext, settings: dict):
        super().__init__(context, settings)

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

        page = await self.new_page()
        screenshots: list[str] = []
        raw_rows: list[dict] = []

        try:
            await page.goto(_BASE_URL, wait_until="domcontentloaded", timeout=30_000)
            await self.human_pause(1000, 2000)

            await self._fill_form(page, origin, destination, depart_date)
            await self.human_pause(2000, 3500)

            # Wait for results
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            await self.scroll_into_results(page)
            await self.human_pause(800, 1500)

            # Screenshot results
            ss_path = screenshot_path(
                self._screenshots_dir, run_date, self.SOURCE,
                origin, destination, depart_date, leg, "results"
            )
            shot = await self.safe_screenshot(page, ss_path)
            if shot:
                screenshots.append(shot)

            raw_rows = await self._extract_cards(page, origin, destination, depart_date, leg, top_n, shot)

        except Exception as e:
            logger.error("GoogleFlights search failed [%s→%s %s %s]: %s", origin, destination, depart_date, leg, e)
        finally:
            await page.close()

        return raw_rows, screenshots

    async def _fill_form(self, page, origin: str, destination: str, date: str) -> None:
        # Set one-way trip
        try:
            trip_type = await page.query_selector('[data-value="2"]')
            if trip_type:
                await trip_type.click()
                await self.human_pause(300, 600)
        except Exception:
            pass

        # Clear and fill origin
        try:
            origin_input = await page.query_selector('input[aria-label*="Where from"]')
            if not origin_input:
                origin_input = await page.query_selector('input[placeholder*="Where from"]')
            if origin_input:
                await origin_input.triple_click()
                await origin_input.type(origin, delay=80)
                await self.human_pause(600, 1000)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                await self.human_pause(400, 700)
        except Exception as e:
            logger.warning("Could not fill origin: %s", e)

        # Fill destination
        try:
            dest_input = await page.query_selector('input[aria-label*="Where to"]')
            if not dest_input:
                dest_input = await page.query_selector('input[placeholder*="Where to"]')
            if dest_input:
                await dest_input.triple_click()
                await dest_input.type(destination, delay=80)
                await self.human_pause(600, 1000)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                await self.human_pause(400, 700)
        except Exception as e:
            logger.warning("Could not fill destination: %s", e)

        # Fill date — click the departure date field
        try:
            date_btn = await page.query_selector('[aria-label*="Departure"]')
            if date_btn:
                await date_btn.click()
                await self.human_pause(500, 900)
                # Type date in MM/DD/YYYY format
                from datetime import date as dobj
                d = dobj.fromisoformat(date)
                formatted = d.strftime("%m/%d/%Y")
                date_input = await page.query_selector('input[placeholder="MM/DD/YYYY"]')
                if date_input:
                    await date_input.fill(formatted)
                    await self.human_pause(300, 500)
                    await page.keyboard.press("Enter")
        except Exception as e:
            logger.warning("Could not fill date: %s", e)

        # Submit search
        try:
            await self.human_pause(500, 800)
            search_btn = await page.query_selector('[aria-label="Search"]')
            if search_btn:
                await search_btn.click()
            else:
                await page.keyboard.press("Enter")
        except Exception as e:
            logger.warning("Could not click search: %s", e)

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
