import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from flightchecker.models import RouteRunResult

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, templates_dir: Path = Path("templates")):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
        )

    def render(
        self,
        route_results: list[RouteRunResult],
        alerts: list[dict],
        report_path: Path,
        run_date: str,
        run_time: str,
        settings: dict,
    ) -> None:
        template = self._env.get_template("daily_report.md.j2")
        time_weight = settings.get("scoring", {}).get("time_weight_usd_per_hour", 15.0)

        content = template.render(
            run_date=run_date,
            run_time=run_time,
            route_results=route_results,
            alerts=alerts,
            time_weight=time_weight,
        )

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(content, encoding="utf-8")
        logger.info("Report written to %s", report_path)
