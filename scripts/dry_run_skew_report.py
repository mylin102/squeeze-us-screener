#!/usr/bin/env python3
"""
Dry-run: generate the skew-enriched email HTML report without sending it.

Loads the latest scan results CSV, runs options skew confirmation (top 50),
renders the HTML template, and writes it to exports/skew/dry_run_report.html.
"""
import csv
import json
import sys
from pathlib import Path

# ── find latest scan result CSV ──────────────────────────────────────────
exports_dir = Path("exports")
csv_files = sorted(exports_dir.glob("**/scan_results_*.csv"))
if not csv_files:
    print("No scan result CSVs found under exports/")
    sys.exit(1)

latest_csv = csv_files[-1]
print(f"Loading scan results from: {latest_csv}")

with open(latest_csv, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    results = list(reader)

print(f"  {len(results)} rows loaded")

# ── options skew (import needs package context) ──────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Also force squeeze module path to this repo
if "squeeze" in sys.modules:
    del sys.modules["squeeze"]
from squeeze.data.options_loader import get_expiry_chain
from squeeze.engine.options_skew import compute_skew
from squeeze.engine.skew_ranker import attach_skew_to_result

TOP_N = 50
candidates = results[:TOP_N]
print(f"Running options skew on top {len(candidates)} candidates...")

skew_enriched = []
for r in candidates:
    ticker = r.get("ticker", "")
    spot_str = r.get("Close", "0")
    try:
        spot = float(spot_str)
    except (ValueError, TypeError):
        continue
    if spot <= 0:
        continue

    chain = get_expiry_chain(ticker)
    if chain is None:
        continue

    # CSV DictReader returns everything as strings — convert numerics
    for numeric_key in ("Close", "composite_score", "momentum", "value_score", "energy_level"):
        if numeric_key in r:
            try:
                r[numeric_key] = float(r[numeric_key])
            except (ValueError, TypeError):
                pass

    skew_data = compute_skew(chain["calls"], chain["puts"], spot)
    enriched = attach_skew_to_result(r, skew_data)
    skew_enriched.append(enriched)

print(f"  Skew computed for {len(skew_enriched)} tickers")

# ── render HTML via exporter ─────────────────────────────────────────────
from squeeze.report.exporter import ReportExporter

extra_sections = {
    "priority": [],
    "houyi": [],
    "whale": [],
    "skew": skew_enriched,
}

exporter = ReportExporter()
html_report = exporter.render_html_summary(
    buy_results=results,
    sell_results=results,
    tracking_buys=[],
    tracking_sells=[],
    extra_sections=extra_sections,
)

# ── write HTML ───────────────────────────────────────────────────────────
skew_dir = Path("exports/skew")
skew_dir.mkdir(parents=True, exist_ok=True)
out_path = skew_dir / "dry_run_report.html"
out_path.write_text(html_report, encoding="utf-8")
print(f"\nHTML report written to: {out_path}")
print("  (Open in browser to preview)")
