import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from jinja2 import Environment, PackageLoader, FileSystemLoader

class ReportExporter:
    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            self.jinja_env = Environment(loader=PackageLoader("squeeze.report", "templates"), autoescape=True)
        else:
            self.jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

    def _get_market_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))

    def export(self, results: List[Dict[str, Any]], output_base_dir: Path) -> Dict[str, Path]:
        now = self._get_market_now()
        date_str = now.strftime("%Y-%m-%d")
        export_dir = output_base_dir / date_str
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%H%M%S")
        csv_path = export_dir / f"scan_results_{timestamp}.csv"
        json_path = export_dir / f"scan_results_{timestamp}.json"
        md_path = export_dir / f"scan_summary_{timestamp}.md"
        self.to_csv(results, csv_path)
        self.to_json(results, json_path)
        self.to_markdown(results, md_path)
        return {"csv": csv_path, "json": json_path, "markdown": md_path}

    def to_csv(self, results: List[Dict[str, Any]], path: Path) -> None:
        if not results: return
        headers = list(results[0].keys())
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(results)

    def to_json(self, results: List[Dict[str, Any]], path: Path) -> None:
        data = {"metadata": {"timestamp": self._get_market_now().isoformat(), "count": len(results)}, "results": results}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_markdown(self, results: List[Dict[str, Any]], path: Path) -> None:
        buy_signals = ["強烈買入 (爆發)", "買入 (動能增強)", "觀察 (跌勢收斂)"]
        sell_signals = ["強烈賣出 (跌破)", "賣出 (動能轉弱)"]
        buy_results = [r for r in results if r.get('Signal') in buy_signals]
        sell_results = [r for r in results if r.get('Signal') in sell_signals]
        content = self.render_summary(buy_results, sell_results)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def render_summary(self, buy_results=None, sell_results=None, tracking_buys=None, tracking_sells=None) -> str:
        template = self.jinja_env.get_template("summary.md.j2")
        top_buys = sorted(buy_results or [], key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        top_sells = sorted(sell_results or [], key=lambda x: x.get('momentum', 0), reverse=False)[:10]
        render_data = {"date": self._get_market_now().strftime("%Y-%m-%d %H:%M:%S") + " (ET)", "buy_results": [self._format_result(r) for r in top_buys], "buy_count": len(buy_results or []), "sell_results": [self._format_result(r) for r in top_sells], "sell_count": len(sell_results or []), "tracking_buys": tracking_buys or [], "tracking_sells": tracking_sells or []}
        return template.render(**render_data)

    def render_html_summary(self, buy_results=None, sell_results=None, tracking_buys=None, tracking_sells=None) -> str:
        template = self.jinja_env.get_template("summary.html.j2")
        top_buys = sorted(buy_results or [], key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        top_sells = sorted(sell_results or [], key=lambda x: x.get('momentum', 0), reverse=False)[:10]
        render_data = {"date": self._get_market_now().strftime("%Y-%m-%d %H:%M:%S") + " (ET)", "buy_results": [self._format_result(r) for r in top_buys], "buy_count": len(buy_results or []), "sell_results": [self._format_result(r) for r in top_sells], "sell_count": len(sell_results or []), "tracking_buys": tracking_buys or [], "tracking_sells": tracking_sells or []}
        return template.render(**render_data)

    def _format_result(self, r: Dict[str, Any]) -> Dict[str, Any]:
        return {"ticker": r.get('ticker'), "name": r.get('name', 'Unknown'), "close": f"{r.get('Close', 0):.2f}", "momentum": r.get('momentum', 0), "energy": r.get('energy_level', 0), "squeeze_active": r.get('is_squeezed', False), "signal": r.get('Signal', 'Neutral')}
