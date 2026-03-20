import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from jinja2 import Environment, PackageLoader, FileSystemLoader


class ReportExporter:
    """
    Orchestrates the export of scan results into multiple formats (CSV, JSON, Markdown).
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            # Use PackageLoader for robust template discovery in installed packages
            self.jinja_env = Environment(
                loader=PackageLoader("squeeze.report", "templates"),
                autoescape=True
            )
        else:
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=True
            )

    def _get_taiwan_now(self) -> datetime:
        """Returns the current time in Taiwan (UTC+8)."""
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    def export(self, results: List[Dict[str, Any]], output_base_dir: Path) -> Dict[str, Path]:
        """
        Exports the results to CSV, JSON, and Markdown files in a date-stamped subdirectory.
        """
        # Create date-stamped subdirectory
        now = self._get_taiwan_now()
        date_str = now.strftime("%Y-%m-%d")
        export_dir = output_base_dir / date_str
        export_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = now.strftime("%H%M%S")
        
        # Define file paths
        csv_path = export_dir / f"scan_results_{timestamp}.csv"
        json_path = export_dir / f"scan_results_{timestamp}.json"
        md_path = export_dir / f"scan_summary_{timestamp}.md"
        
        # Execute exports
        self.to_csv(results, csv_path)
        self.to_json(results, json_path)
        self.to_markdown(results, md_path)
        
        return {
            "csv": csv_path,
            "json": json_path,
            "markdown": md_path
        }

    def to_csv(self, results: List[Dict[str, Any]], path: Path) -> None:
        """Saves results to a flat CSV file."""
        if not results:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                f.write("")
            return

        headers = list(results[0].keys())
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(results)

    def to_json(self, results: List[Dict[str, Any]], path: Path) -> None:
        """Saves results to JSON with metadata (timestamp, patterns)."""
        data = {
            "metadata": {
                "timestamp": self._get_taiwan_now().isoformat(),
                "count": len(results),
            },
            "results": results
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_markdown(self, results: List[Dict[str, Any]], path: Path) -> None:
        """Renders the Markdown summary using Jinja2."""
        content = self.render_summary(results)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def render_summary(self, results: List[Dict[str, Any]], 
                       perf_results: Optional[List[Dict[str, Any]]] = None,
                       active_tracking: Optional[List[Dict[str, Any]]] = None) -> str:
        """Renders the summary content as a string, filtering for Buy signals."""
        template = self.jinja_env.get_template("summary.md.j2")

        # Define targeted buy signals
        buy_signals = ["強烈買入 (爆發)", "買入 (動能增強)", "觀察 (跌勢收斂)"]

        # Filter results: only those with specific buy signals
        filtered_results = [r for r in results if r.get('Signal') in buy_signals]
        filtered_results = sorted(filtered_results, key=lambda x: x.get('momentum', 0), reverse=True)

        top_picks = filtered_results[:10] if len(filtered_results) > 10 else filtered_results

        render_data = {
            "date": self._get_taiwan_now().strftime("%Y-%m-%d %H:%M:%S") + " (TST)",
            "results": [self._format_result(r) for r in filtered_results],
            "top_picks": [self._format_result(r) for r in top_picks],
            "count": len(filtered_results),
            "perf_results": perf_results or [],
            "active_tracking": active_tracking or []
        }

        return template.render(**render_data)

    def _format_result(self, r: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures common keys exist for the template."""
        return {
            "ticker": r.get('ticker'),
            "name": r.get('name', '未知'),
            "close": f"{r.get('Close', 0):.2f}",
            "momentum": r.get('momentum') or r.get('daily_momentum') or 0,
            "energy": r.get('energy_level', 0),
            "squeeze_active": r.get('is_squeezed') or r.get('is_houyi') or r.get('is_whale'),
            "signal": r.get('Signal', '觀望')
        }
