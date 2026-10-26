from pathlib import Path


def screenshot_path(
    screenshots_dir: str,
    run_date: str,
    source: str,
    origin: str,
    destination: str,
    date: str,
    leg: str,
    label: str,
) -> Path:
    """Return an absolute Path for a screenshot file, creating parent dirs."""
    base = Path(screenshots_dir) / run_date
    base.mkdir(parents=True, exist_ok=True)
    filename = f"{source}_{origin}_{destination}_{leg}_{date}_{label}.png"
    return base / filename
