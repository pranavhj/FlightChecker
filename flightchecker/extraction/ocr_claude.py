import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROMPT = """\
Use the Read tool to view the screenshot at: {image_path}

Extract all visible flight results and return ONLY a JSON array. Each element must have exactly these keys:
  price_text, airline_text, duration_text, stops_text, dep_time_text, arr_time_text

Use "" for any field you cannot read clearly. Raw JSON array only — no explanation, no markdown.
"""


class ClaudeVisionOCR:
    def __init__(self, settings: dict):
        ocr_cfg = settings.get("ocr", {})
        scripts_env = ocr_cfg.get("openclaw_scripts_dir_env", "OPENCLAW_SCRIPTS_DIR")
        scripts_dir = os.environ.get(scripts_env, "")
        self._agent_smart = Path(scripts_dir) / "agent-smart.py" if scripts_dir else None
        self._model = ocr_cfg.get("claude_model", "haiku")

    def extract(self, screenshot_path: str) -> Optional[list[dict]]:
        path = Path(screenshot_path)
        if not path.exists():
            return None
        if not self._agent_smart or not self._agent_smart.exists():
            logger.warning("agent-smart.py not found; set OPENCLAW_SCRIPTS_DIR env var")
            return None

        prompt = _PROMPT.format(image_path=str(path.resolve()))
        prompt_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(prompt)
                prompt_file = Path(f.name)

            result = subprocess.run(
                [sys.executable, str(self._agent_smart),
                 '--permission-mode', 'bypassPermissions',
                 '--model', self._model,
                 '--print-file', str(prompt_file)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=60,
            )
            return _parse_json(result.stdout)
        except Exception as e:
            logger.warning("Claude delegation OCR failed: %s", e)
            return None
        finally:
            if prompt_file:
                try:
                    prompt_file.unlink(missing_ok=True)
                except Exception:
                    pass


def _parse_json(text: str) -> Optional[list[dict]]:
    if '```' in text:
        m = re.search(r'```(?:json)?\s*([\s\S]+?)```', text)
        if m:
            text = m.group(1).strip()
    m = re.search(r'\[[\s\S]+\]', text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None
