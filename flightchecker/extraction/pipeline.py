import logging
from typing import Optional

from flightchecker.extraction.ocr_claude import ClaudeVisionOCR
from flightchecker.extraction.ocr_easyocr import EasyOCRExtractor
from flightchecker.models import FlightResult

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ["price_text", "airline_text", "duration_text", "dep_time_text"]


def _is_complete(row: FlightResult) -> bool:
    return all(getattr(row, f, "") for f in _REQUIRED_FIELDS)


def _dict_to_result(d: dict, template: FlightResult, method: str, confidence: str) -> FlightResult:
    return FlightResult(
        source=template.source,
        origin=template.origin,
        destination=template.destination,
        depart_date=template.depart_date,
        leg=template.leg,
        price_text=d.get("price_text", ""),
        duration_text=d.get("duration_text", ""),
        stops_text=d.get("stops_text", ""),
        airline_text=d.get("airline_text", ""),
        dep_time_text=d.get("dep_time_text", ""),
        arr_time_text=d.get("arr_time_text", ""),
        baggage_text=d.get("baggage_text", ""),
        confidence=confidence,
        screenshot_path=template.screenshot_path,
        extraction_method=method,
    )


class ExtractionPipeline:
    def __init__(self, settings: dict):
        self._claude = ClaudeVisionOCR(settings)
        langs = settings.get("ocr", {}).get("easyocr_languages", ["en"])
        self._easyocr = EasyOCRExtractor(languages=langs)

    def process(self, results: list[FlightResult]) -> list[FlightResult]:
        """
        For each result that is incomplete, attempt OCR upgrades.
        Results that pass DOM extraction unchanged stay as-is.
        """
        processed = []
        ocr_claude_cache: dict[str, Optional[list[dict]]] = {}
        ocr_easy_cache: dict[str, Optional[list[dict]]] = {}

        for r in results:
            if _is_complete(r):
                processed.append(r)
                continue

            # Tier 2: Claude vision
            shot = r.screenshot_path
            if shot and shot not in ocr_claude_cache:
                ocr_claude_cache[shot] = self._claude.extract(shot)

            claude_rows = ocr_claude_cache.get(shot)
            if claude_rows:
                upgraded = self._pick_best(claude_rows, r, "ocr_claude", "medium")
                if upgraded and _is_complete(upgraded):
                    processed.append(upgraded)
                    continue

            # Tier 3: easyocr
            if shot and shot not in ocr_easy_cache:
                ocr_easy_cache[shot] = self._easyocr.extract(shot)

            easy_rows = ocr_easy_cache.get(shot)
            if easy_rows:
                upgraded = self._pick_best(easy_rows, r, "ocr_easyocr", "low")
                if upgraded:
                    processed.append(upgraded)
                    continue

            # Tier 4: manual review
            r.confidence = "manual_review"
            r.extraction_method = "manual_review"
            processed.append(r)

        return processed

    def _pick_best(
        self,
        rows: list[dict],
        template: FlightResult,
        method: str,
        confidence: str,
    ) -> Optional[FlightResult]:
        if not rows:
            return None
        # Prefer a row that at least has price_text
        for row in rows:
            if row.get("price_text"):
                return _dict_to_result(row, template, method, confidence)
        return _dict_to_result(rows[0], template, method, confidence)
