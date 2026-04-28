import pytest
from flightchecker.models import FlightResult, RouteConfig


@pytest.fixture
def sample_route():
    return RouteConfig(
        origin="SJC",
        destination="LAS",
        one_way=False,
        outbound_window={"start": "2026-05-01", "end": "2026-05-02"},
        return_window={"start": "2026-05-08", "end": "2026-05-09"},
    )


def make_result(**kwargs) -> FlightResult:
    defaults = dict(
        source="google_flights",
        origin="SJC",
        destination="LAS",
        depart_date="2026-05-01",
        leg="outbound",
        price_text="$189",
        duration_text="1h 30m",
        stops_text="Nonstop",
        airline_text="Southwest",
        dep_time_text="7:00 AM",
        arr_time_text="8:30 AM",
        confidence="high",
        screenshot_path="",
        extraction_method="dom",
    )
    defaults.update(kwargs)
    return FlightResult(**defaults)
