import pytest
from unittest.mock import patch, MagicMock

from flightchecker.extraction.pipeline import ExtractionPipeline, _is_complete
from tests.conftest import make_result


SETTINGS = {
    "ocr": {
        "primary": "claude_vision",
        "claude_model": "haiku",
        "openclaw_scripts_dir_env": "OPENCLAW_SCRIPTS_DIR",
        "easyocr_languages": ["en"],
    }
}


def test_is_complete_true():
    r = make_result()
    assert _is_complete(r) is True


def test_is_complete_missing_field():
    r = make_result(airline_text="")
    assert _is_complete(r) is False


def test_pipeline_passes_complete_results():
    pipeline = ExtractionPipeline(SETTINGS)
    r = make_result()
    result = pipeline.process([r])
    assert len(result) == 1
    assert result[0].extraction_method == "dom"
    assert result[0].confidence == "high"


def test_pipeline_falls_back_to_claude():
    pipeline = ExtractionPipeline(SETTINGS)
    incomplete = make_result(airline_text="", screenshot_path="/fake/shot.png")

    claude_data = [{
        "price_text": "$189",
        "airline_text": "Southwest",
        "duration_text": "1h 30m",
        "stops_text": "Nonstop",
        "dep_time_text": "7:00 AM",
        "arr_time_text": "8:30 AM",
    }]
    with patch.object(pipeline._claude, "extract", return_value=claude_data):
        result = pipeline.process([incomplete])

    assert len(result) == 1
    assert result[0].extraction_method == "ocr_claude"
    assert result[0].airline_text == "Southwest"


def test_pipeline_falls_back_to_easyocr_when_claude_fails():
    pipeline = ExtractionPipeline(SETTINGS)
    incomplete = make_result(airline_text="", dep_time_text="", screenshot_path="/fake/shot.png")

    easy_data = [{
        "price_text": "$189",
        "airline_text": "",
        "duration_text": "1h 30m",
        "stops_text": "",
        "dep_time_text": "7:00 AM",
        "arr_time_text": "8:30 AM",
    }]
    with patch.object(pipeline._claude, "extract", return_value=None):
        with patch.object(pipeline._easyocr, "extract", return_value=easy_data):
            result = pipeline.process([incomplete])

    assert result[0].extraction_method == "ocr_easyocr"


def test_pipeline_marks_manual_review_when_all_fail():
    pipeline = ExtractionPipeline(SETTINGS)
    incomplete = make_result(price_text="", airline_text="", dep_time_text="", screenshot_path="")

    with patch.object(pipeline._claude, "extract", return_value=None):
        with patch.object(pipeline._easyocr, "extract", return_value=None):
            result = pipeline.process([incomplete])

    assert result[0].confidence == "manual_review"
    assert result[0].extraction_method == "manual_review"
