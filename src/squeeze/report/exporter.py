import csv
import json
import tomllib
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

    def _get_app_version(self) -> str:
        pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
        try:
            with open(pyproject_path, "rb") as f:
                return tomllib.load(f)["project"]["version"]
        except Exception:
            return "unknown"

    def export(self, results: List[Dict[str, Any]], output_base_dir: Path, extra_sections: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, Path]:
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
        self.to_markdown(results, md_path, extra_sections=extra_sections)
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

    def to_markdown(self, results: List[Dict[str, Any]], path: Path, extra_sections: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        buy_signals = ["強烈買入 (爆發)", "買入 (動能增強)", "觀察 (跌勢收斂)"]
        sell_signals = ["強烈賣出 (跌破)", "賣出 (動能轉弱)"]
        buy_results = [r for r in results if r.get('Signal') in buy_signals]
        sell_results = [r for r in results if r.get('Signal') in sell_signals]
        content = self.render_summary(buy_results, sell_results, extra_sections=extra_sections)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def render_summary(self, buy_results=None, sell_results=None, tracking_buys=None, tracking_sells=None, extra_sections: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> str:
        template = self.jinja_env.get_template("summary.md.j2")
        top_buys = sorted(buy_results or [], key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        top_sells = sorted(sell_results or [], key=lambda x: x.get('momentum', 0), reverse=False)[:10]
        extra_sections = extra_sections or {}
        top_priority = sorted(extra_sections.get("priority", []), key=lambda x: (x.get('composite_score', 0), x.get('momentum', 0)), reverse=True)[:10]
        top_houyi = sorted(extra_sections.get("houyi", []), key=lambda x: x.get('rally_pct', 0), reverse=True)[:10]
        top_whale = sorted(extra_sections.get("whale", []), key=lambda x: x.get('weekly_momentum', 0), reverse=True)[:10]
        render_data = {"date": self._get_market_now().strftime("%Y-%m-%d %H:%M:%S") + " (ET)", "app_version": self._get_app_version(), "buy_results": [self._format_result(r) for r in top_buys], "buy_count": len(buy_results or []), "sell_results": [self._format_result(r) for r in top_sells], "sell_count": len(sell_results or []), "tracking_buys": self._summarize_tracking_positions(tracking_buys or []), "tracking_sells": tracking_sells or [], "priority_results": [self._format_result(r) for r in top_priority], "priority_count": len(extra_sections.get("priority", [])), "houyi_results": [self._format_result(r) for r in top_houyi], "houyi_count": len(extra_sections.get("houyi", [])), "whale_results": [self._format_result(r) for r in top_whale], "whale_count": len(extra_sections.get("whale", []))}
        return template.render(**render_data)

    def render_html_summary(self, buy_results=None, sell_results=None, tracking_buys=None, tracking_sells=None, extra_sections: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> str:
        template = self.jinja_env.get_template("summary.html.j2")
        top_buys = sorted(buy_results or [], key=lambda x: x.get('momentum', 0), reverse=True)[:10]
        top_sells = sorted(sell_results or [], key=lambda x: x.get('momentum', 0), reverse=False)[:10]
        extra_sections = extra_sections or {}
        top_priority = sorted(extra_sections.get("priority", []), key=lambda x: (x.get('composite_score', 0), x.get('momentum', 0)), reverse=True)[:10]
        top_houyi = sorted(extra_sections.get("houyi", []), key=lambda x: x.get('rally_pct', 0), reverse=True)[:10]
        top_whale = sorted(extra_sections.get("whale", []), key=lambda x: x.get('weekly_momentum', 0), reverse=True)[:10]
        render_data = {"date": self._get_market_now().strftime("%Y-%m-%d %H:%M:%S") + " (ET)", "app_version": self._get_app_version(), "buy_results": [self._format_result(r) for r in top_buys], "buy_count": len(buy_results or []), "sell_results": [self._format_result(r) for r in top_sells], "sell_count": len(sell_results or []), "tracking_buys": self._summarize_tracking_positions(tracking_buys or []), "tracking_sells": tracking_sells or [], "priority_results": [self._format_result(r) for r in top_priority], "priority_count": len(extra_sections.get("priority", [])), "houyi_results": [self._format_result(r) for r in top_houyi], "houyi_count": len(extra_sections.get("houyi", [])), "whale_results": [self._format_result(r) for r in top_whale], "whale_count": len(extra_sections.get("whale", []))}
        return template.render(**render_data)

    def _summarize_tracking_positions(self, tracking_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in tracking_rows:
            ticker = row.get("ticker")
            if not ticker:
                continue
            grouped.setdefault(ticker, []).append(row)

        summaries = []
        for ticker, rows in grouped.items():
            ordered_rows = sorted(
                rows,
                key=lambda item: (item.get("date") or "", item.get("last_updated") or ""),
                reverse=True,
            )
            latest = dict(ordered_rows[0])
            entry_prices = [float(item["entry_price"]) for item in ordered_rows if item.get("entry_price") is not None]
            latest["entries"] = len(ordered_rows)
            latest["avg_entry_price"] = (sum(entry_prices) / len(entry_prices)) if entry_prices else latest.get("entry_price")
            latest["latest_entry_date"] = latest.get("date")
            stop_loss_messages = [str(item.get("stop_loss_message")) for item in ordered_rows if item.get("stop_loss_message")]
            latest["stop_loss_triggered"] = bool(stop_loss_messages)
            latest["stop_loss_message"] = stop_loss_messages[0] if stop_loss_messages else ""
            summaries.append(latest)

        return sorted(
            summaries,
            key=lambda item: (item.get("latest_entry_date") or "", item.get("ticker") or ""),
            reverse=True,
        )

    def _format_result(self, r: Dict[str, Any]) -> Dict[str, Any]:
        return {"ticker": r.get('ticker'), "name": r.get('name', 'Unknown'), "close": f"{r.get('Close', 0):.2f}", "momentum": r.get('momentum', 0), "energy": r.get('energy_level', 0), "squeeze_active": r.get('is_squeezed', False), "signal": r.get('Signal', 'Neutral'), "has_houyi": r.get('has_houyi', False), "has_whale": r.get('has_whale', False), "composite_score": r.get('composite_score', 0)}
