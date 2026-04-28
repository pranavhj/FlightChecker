import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a flight data extractor. Given a screenshot of flight search results,
extract the top flights visible and return a JSON array. Each element must have exactly these keys:
  price_text, airline_text, duration_text, stops_text, dep_time_text, arr_time_text

Use empty string "" for any field you cannot read clearly. Return ONLY the JSON array, no other text."""


class ClaudeVisionOCR:
    def __init__(self, settings: dict):
        ocr_cfg = settings.get("ocr", {})
        self.model = ocr_cfg.get("claude_model", "claude-haiku-4-5-20251001")
        api_key_env = ocr_cfg.get("anthropic_api_key_env", "ANTHROPIC_API_KEY")
        self._api_key = os.environ.get(api_key_env)

    def _client(self):
        import anthropic
        return anthropic.Anthropic(api_key=self._api_key)

    def extract(self, screenshot_path: str) -> Optional[list[dict]]:
        if not self._api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping Claude OCR")
            return None
        path = Path(screenshot_path)
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            client = self._client()
            response = client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": "Extract all flight results visible in this screenshot."},
                    ],
                }],
            )
            raw = response.content[0].text.strip()
            # Strip ```json ... ``` wrapping if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            logger.warning("Claude OCR failed: %s", e)
            return None
