import asyncio
import logging
import random
from pathlib import Path

from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)


class BaseScraper:
    def __init__(self, context: BrowserContext, settings: dict):
        self.context = context
        self.settings = settings
        self._screenshots_dir = settings["output"]["screenshots_dir"]

    async def new_page(self) -> Page:
        page = await self.context.new_page()
        ua = self.settings["browser"].get("user_agent", "")
        if ua:
            await page.set_extra_http_headers({"User-Agent": ua})
        return page

    async def human_pause(self, min_ms: int = 800, max_ms: int = 2500) -> None:
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

    async def safe_screenshot(self, page: Page, path: Path) -> str:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception as e:
            logger.warning("Screenshot failed for %s: %s", path, e)
            return ""

    async def scroll_into_results(self, page: Page, steps: int = 5) -> None:
        for _ in range(steps):
            await page.keyboard.press("PageDown")
            await asyncio.sleep(0.4)

    async def try_selectors(self, page: Page, selectors: list[str]) -> list:
        """Return elements from the first selector that yields results."""
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                if elements:
                    return elements
            except Exception:
                continue
        return []

    async def get_text(self, element, selectors: list[str]) -> str:
        """Try selectors within an element, return first non-empty text."""
        for sel in selectors:
            try:
                el = await element.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    text = text.strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""
