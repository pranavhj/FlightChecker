"""
CSS selector fallback lists per source and field.

These selectors are the highest-churn part of the codebase — Google Flights and
Skyscanner update their DOM frequently. When the extraction_method distribution
in reports shifts from 'dom' toward 'ocr_claude', update these lists.

Each entry is a list of selectors tried in order; the first non-empty match wins.
"""

SELECTORS: dict[str, dict[str, list[str]]] = {
    "google_flights": {
        # Flight result card container
        "card": [
            "li.pIav2d",
            "[data-ved] li[jscontroller]",
            "li[jsname]",
        ],
        # Price field within a card
        "price": [
            ".YMlIz.FpEdX",
            ".YMlIz",
            "[data-gs] .BVAVmf",
            ".U3gSDe .FpEdX",
        ],
        # Airline name
        "airline": [
            ".h1fkLb .sSHqwe span[aria-label]",
            ".Ir0Voe .sSHqwe span[aria-label]",
            ".h1fkLb span[aria-label]",
            ".sSHqwe span[aria-label]",
        ],
        # Duration
        "duration": [
            ".gvkrdb",
            ".AdWm1c.gvkrdb",
            "[data-gs] .AdWm1c",
        ],
        # Stops / nonstop
        "stops": [
            ".EfT7Ae span",
            ".stops-count span",
            ".ogfYpf",
            ".EfT7Ae .ogfYpf",
        ],
        # Departure time
        "dep_time": [
            ".wtdjmc span[aria-label]",
            ".Ir0Voe span[aria-label]",
            ".eoY5cb span[aria-label]",
            "span[aria-label*='Departure time']",
        ],
        # Arrival time
        "arr_time": [
            ".XWcVob span[aria-label]",
            ".nI6Cpc span[aria-label]",
            "span[aria-label*='Arrival time']",
        ],
    },
    "skyscanner": {
        "card": [
            "[class*='FlightsTicket']",
            "[data-testid='flight-card']",
            ".BpkCard_bpk-card__eab6",
        ],
        "price": [
            "[class*='Price__value']",
            "[data-testid='price-label']",
            "[class*='price-label']",
        ],
        "airline": [
            "[class*='LogoImage'] img[alt]",
            "[data-testid='carrier-name']",
            "[class*='Carriers__name']",
        ],
        "duration": [
            "[class*='Duration__duration']",
            "[data-testid='duration']",
            "[class*='duration-container'] span",
        ],
        "stops": [
            "[class*='Stops__stops']",
            "[data-testid='stops-label']",
            "[class*='stops-label']",
        ],
        "dep_time": [
            "[class*='LegInfo__departTime']",
            "[data-testid='departure-time']",
            "[class*='departure-time']",
        ],
        "arr_time": [
            "[class*='LegInfo__arriveTime']",
            "[data-testid='arrival-time']",
            "[class*='arrival-time']",
        ],
    },
}
