from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FlightResult:
    source: str           # "google_flights" | "skyscanner"
    origin: str           # "SJC"
    destination: str      # "LAS"
    depart_date: str      # "YYYY-MM-DD"
    leg: str              # "outbound" | "return" | "oneway"
    price_text: str       # "$189"
    duration_text: str    # "2h 15m"
    stops_text: str       # "Nonstop"
    airline_text: str     # "United"
    dep_time_text: str    # "6:00 AM"
    arr_time_text: str    # "8:15 AM"
    confidence: str       # "high" | "medium" | "low" | "manual_review"
    screenshot_path: str
    extraction_method: str  # "dom" | "ocr_claude" | "ocr_easyocr" | "manual_review"
    price_usd: Optional[float] = None
    total_hours: Optional[float] = None
    score: Optional[float] = None


@dataclass
class RouteConfig:
    origin: str
    destination: str
    one_way: bool
    outbound_window: dict   # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    return_window: Optional[dict] = None  # only set when one_way=False


@dataclass
class LegPairing:
    """Best combination of outbound + return FlightResult for a return route."""
    outbound: FlightResult
    ret: FlightResult
    total_price_usd: float
    combined_score: float


@dataclass
class RouteRunResult:
    route: RouteConfig
    source: str
    outbound_results: list = field(default_factory=list)   # list[FlightResult]
    return_results: list = field(default_factory=list)     # list[FlightResult] or []
    best_pairings: list = field(default_factory=list)      # list[LegPairing] for return routes
    warnings: list = field(default_factory=list)           # list[str]
