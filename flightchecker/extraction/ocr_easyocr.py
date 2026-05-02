import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRICE_RE = re.compile(r"\$([\d,]+)")
DURATION_RE = re.compile(r"(\d+h\s*\d*m?)")
TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*[AP]M", re.IGNORECASE)


class EasyOCRExtractor:
    def __init__(self, languages: list[str] = None):
        self._languages = languages or ["en"]
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self._languages, gpu=False)
        return self._reader

    def extract(self, screenshot_path: str) -> Optional[list[dict]]:
        path = Path(screenshot_path)
        if not path.exists():
            return None
        try:
            reader = self._get_reader()
            raw_lines = reader.readtext(str(path), detail=0)
            text = " ".join(raw_lines)

            prices = PRICE_RE.findall(text)
            durations = DURATION_RE.findall(text)
            times = TIME_RE.findall(text)

            results = []
            count = max(len(prices), 1)
            for i in range(count):
                results.append({
                    "price_text": f"${prices[i]}" if i < len(prices) else "",
                    "airline_text": "",  # easyocr can't reliably parse airline logos/names
                    "duration_text": durations[i] if i < len(durations) else "",
                    "stops_text": "",
                    "dep_time_text": times[i * 2] if i * 2 < len(times) else "",
                    "arr_time_text": times[i * 2 + 1] if i * 2 + 1 < len(times) else "",
                    "baggage_text": "",  # easyocr can't reliably parse baggage policies
                })
            return results if results else None
        except Exception as e:
            logger.warning("EasyOCR failed: %s", e)
            return None
