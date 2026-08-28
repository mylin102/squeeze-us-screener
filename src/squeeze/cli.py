# Updated to support RS/MA20 indicators, score versions, data-quality, and nightly commands from Taiwan screener
import typer
import pandas as pd
from rich.console import Console
from rich.table import Table
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from squeeze.data.tickers import fetch_tickers_with_names
from squeeze.report.exporter import ReportExporter
from squeeze.report.notifier import LineNotifier, EmailNotifier
from squeeze.report.performance import PerformanceTracker
from squeeze.report.tracking_analysis import build_tracking_report, format_tracking_report, load_tracking_frame
from squeeze.engine.ranker import enrich_with_scores
from squeeze.engine.scanner import MarketScanner, SPY_TICKER

app = typer.Typer(help="Squeeze Stock Screener for US Market")
console = Console()


def _attach_pattern_flags(results, houyi_results, whale_results):
    """Cross-reference houyi/whale matches and call ranker for final scores."""
    houyi_map = {r["ticker"]: r for r in houyi_results if r.get("is_houyi")}
    whale_map = {r["ticker"]: r for r in whale_results if r.get("is_whale")}
    enriched = []
    for result in results:
        ticker = result.get("ticker")
        row = dict(result)
        row["has_houyi"] = ticker in houyi_map
        row["has_whale"] = ticker in whale_map
        enriched.append(row)
    # Let ranker compute all scores (v1, v2) consistently
    return enrich_with_scores(enriched)


@app.command(name="analyze-tracking")
def analyze_tracking(
    csv_path: Path = typer.Option(Path("recommendations.csv"), "--csv", help="Tracking CSV to analyze."),
):
    """Analyze completed tracking history and summarize strategy health."""
    report = build_tracking_report(load_tracking_frame(str(csv_path)))
    console.print(format_tracking_report(report))


@app.command(name="analyze")
def analyze(
    ticker: str = typer.Option(..., "--ticker", help="Single US ticker to analyze."),
    pattern: str = typer.Option("squeeze", "--pattern", "-P", help="Pattern to analyze (squeeze, houyi, whale)"),
    period: str = typer.Option("2y", "--period", "-p", help="Data period (e.g., 2y, 1y, 6mo)"),
    fundamentals: bool = typer.Option(True, "--fundamentals/--no-fundamentals", help="Include fundamentals if available."),
):
    """Analyze a single US ticker and print the latest pattern state."""
    from squeeze.engine.patterns import detect_squeeze, detect_houyi_shooting_sun, detect_whale_trading
    from squeeze.engine.scanner import MarketScanner

    pattern_map = {
        "squeeze": ("Squeeze", detect_squeeze),
        "houyi": ("Houyi Shooting the Sun", detect_houyi_shooting_sun),
        "whale": ("Whale Trading", detect_whale_trading),
    }

    normalized_ticker = ticker.strip().upper()
    if pattern not in pattern_map:
        console.print(f"[red]Unknown pattern: {pattern}.[/red]")
        raise typer.Exit(code=1)

    pattern_title, pattern_fn = pattern_map[pattern]
    ticker_map = fetch_tickers_with_names()
    scanner = MarketScanner([normalized_ticker], ticker_names=ticker_map)

    with console.status(f"[bold green]Downloading market data for {normalized_ticker}...[/bold green]"):
        scanner.fetch_data(period=period)

    if scanner.data.empty:
        console.print(f"[red]No market data available for {normalized_ticker}.[/red]")
        raise typer.Exit(code=1)

    if fundamentals:
        with console.status(f"[bold green]Fetching fundamentals for {normalized_ticker}...[/bold green]"):
            scanner.fetch_fundamentals()

    # Fetch benchmark for RS
    with console.status("[bold green]Fetching benchmark (SPY)...[/bold green]"):
        scanner.fetch_benchmark(period=period)
        bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None

    results = scanner.scan(pattern_fn, benchmark_close=bm_close)
    if not results:
        console.print(f"[red]No analysis result produced for {normalized_ticker}.[/red]")
        raise typer.Exit(code=1)

    result = results[0]
    table = Table(title=f"{pattern_title} Analysis: {normalized_ticker}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    display_rows = [
        ("Ticker", result.get("ticker", normalized_ticker)),
        ("Name", result.get("name", ticker_map.get(normalized_ticker, "Unknown"))),
        ("Signal", result.get("Signal", "觀望")),
        ("Close", f"{result.get('Close', 0.0):.2f}" if result.get("Close") is not None else "N/A"),
        ("Squeeze On", "Yes" if result.get("squeeze_on") else "No"),
        ("Fired", "Yes" if result.get("fired") else "No"),
        ("Energy Level", str(result.get("energy_level", 0))),
        ("Momentum", f"{result.get('momentum', 0.0):.4f}"),
        ("Prev Momentum", f"{result.get('prev_momentum', 0.0):.4f}"),
        ("MA20", f"{result.get('ma20', 0.0):.2f}" if result.get("ma20") is not None else "N/A"),
        ("Close Above MA20", "Yes" if result.get("close_above_ma20") else "No"),
    ]

    if pattern == "houyi":
        display_rows.extend([
            ("Houyi Match", "Yes" if result.get("is_houyi") else "No"),
            ("Rally %", f"{result.get('rally_pct', 0.0):.2%}"),
            ("Fib Level", f"{result.get('fib_level', 0.0):.3f}"),
            ("Shooting Star", "Yes" if result.get("shooting_star") else "No"),
        ])
    elif pattern == "whale":
        display_rows.extend([
            ("Whale Match", "Yes" if result.get("is_whale") else "No"),
            ("Daily Squeeze", "Yes" if result.get("daily_squeeze") else "No"),
            ("Weekly Squeeze", "Yes" if result.get("weekly_squeeze") else "No"),
            ("Daily Momentum", f"{result.get('daily_momentum', 0.0):.4f}"),
            ("Weekly Momentum", f"{result.get('weekly_momentum', 0.0):.4f}"),
        ])
    else:
        display_rows.extend([
            ("Squeeze Match", "Yes" if (result.get("is_squeezed") or result.get("fired")) else "No"),
            ("Timestamp", result.get("timestamp", "N/A")),
        ])

    # RS fields display if available
    if "rs_index" in result and pd.notna(result["rs_index"]):
        display_rows.extend([
            ("RS Index (Base 100)", f"{result['rs_index']:.2f}"),
            ("RS Slope (5D)", f"{result['rs_slope_5d']:.4f}%"),
            ("RS New High (60D)", "Yes" if result['rs_new_high_60'] else "No"),
            ("RS Signal", result.get("rs_signal", "Neutral")),
        ])

    fundamentals_map = {
        "marketCap": "Market Cap",
        "averageVolume": "Average Volume",
        "trailingPE": "Trailing PE",
        "priceToBook": "Price/Book",
        "dividendYield": "Dividend Yield",
        "value_score": "Value Score",
        "ranking_score": "Ranking Score (v1)",
        "experimental_score": "Experimental Score (v2)",
    }
    for key, label in fundamentals_map.items():
        if key in result and pd.notna(result[key]):
            value = result[key]
            if key == "marketCap":
                value = f"{float(value) / 1e9:.2f}B"
            elif key == "dividendYield":
                value = f"{float(value):.2%}"
            elif isinstance(value, float):
                value = f"{value:.2f}"
            display_rows.append((label, str(value)))

    for field, value in display_rows:
        table.add_row(field, value)

    console.print(table)


@app.command(name="plot")
def plot(
    ticker: str = typer.Option(..., "--ticker", help="Single US ticker to plot."),
    period: str = typer.Option("2y", "--period", "-p", help="Data period (e.g., 2y, 1y, 6mo)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output PNG path."),
    rs: bool = typer.Option(True, "--rs/--no-rs", help="Include RS (Relative Strength) panel."),
):
    """Generate a chart for a single US ticker."""
    from squeeze.engine.scanner import MarketScanner
    from squeeze.report.visualizer import plot_ticker

    normalized_ticker = ticker.strip().upper()
    ticker_map = fetch_tickers_with_names()
    scanner = MarketScanner([normalized_ticker], ticker_names=ticker_map)

    with console.status(f"[bold green]Downloading market data for {normalized_ticker}...[/bold green]"):
        scanner.fetch_data(period=period)

    if scanner.data.empty:
        console.print(f"[red]No market data available for {normalized_ticker}.[/red]")
        raise typer.Exit(code=1)

    bm_close = None
    if rs:
        with console.status("[bold green]Fetching benchmark (SPY) for RS...[/bold green]"):
            scanner.fetch_benchmark(period=period)
            bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None

    if isinstance(scanner.data.columns, pd.MultiIndex):
        ticker_df = scanner.data[normalized_ticker].dropna(subset=["Close"])
    else:
        ticker_df = scanner.data.dropna(subset=["Close"])

    if ticker_df.empty:
        console.print(f"[red]No plottable data available for {normalized_ticker}.[/red]")
        raise typer.Exit(code=1)

    chart_path = output or Path("exports") / "single" / f"{normalized_ticker}.png"
    plot_ticker(ticker_df, normalized_ticker, str(chart_path), benchmark_close=bm_close)
    console.print(f"[green]Saved chart:[/green] {chart_path}")


@app.command(name="scan")
def scan(
    pattern: str = typer.Option("squeeze", "--pattern", "-P", help="Pattern to scan for (squeeze, houyi, whale)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit the number of tickers to scan (for testing)"),
    period: str = typer.Option("2y", "--period", "-p", help="Data period (e.g., 2y, 1y, 6mo)"),
    export: bool = typer.Option(False, "--export", "-e", help="Export results to CSV/JSON/MD"),
    plot: bool = typer.Option(False, "--plot", help="Generate charts for top picks"),
    top: int = typer.Option(10, "--top", help="Number of top picks to plot"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Output directory for reports and charts"),
    notify: bool = typer.Option(False, "--notify", help="Send notification summary (e.g., via LINE)"),
    min_mkt_cap: Optional[float] = typer.Option(None, "--min-mkt-cap", help="Minimum market capitalization (in billion USD)"),
    min_volume: Optional[float] = typer.Option(None, "--min-volume", help="Minimum average daily volume"),
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Minimum Value Score (0.0 - 1.0)"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum stock price (USD)"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum stock price (USD)"),
    tracking_stop_loss_pct: Optional[float] = typer.Option(None, "--tracking-stop-loss-pct", help="Attach a fixed stop-loss alert percentage to tracked buy positions."),
    tracking_stop_loss_ma_window: Optional[int] = typer.Option(None, "--tracking-stop-loss-ma-window", help="Attach a moving-average stop-loss alert window to tracked buy positions."),
    tracking_stop_loss_ticks: int = typer.Option(0, "--tracking-stop-loss-ticks", help="Attach a tick offset below the moving average for tracked buy stop-loss alerts."),
    with_options_skew: bool = typer.Option(False, "--with-options-skew", help="Enable options skew confirmation for top squeeze candidates."),
    top_n_options: int = typer.Option(50, "--top-n-options", help="Number of top squeeze candidates to run options skew on (only when --with-options-skew)."),
    score_version: str = typer.Option("v1", "--score-version", help="Ranking score version: v1 (Rank, production 0-6) or v2 (Exp, experimental +RS 0-9)"),
):
    """
    Scan all US stocks for specific technical patterns and fundamental filters.
    """
    from squeeze.engine.patterns import detect_squeeze, detect_houyi_shooting_sun, detect_whale_trading
    from squeeze.engine.scanner import MarketScanner
    from squeeze.report.visualizer import plot_ticker

    console.print(f"[yellow]Scanning for {pattern} pattern in US Market...[/yellow]")
    
    pattern_map = {
        "squeeze": {
            "fn": detect_squeeze,
            "filter": lambda r: r.get('is_squeezed') or r.get('fired'),
            "title": "Squeeze Scan Results",
            "sort_key": lambda x: x.get('energy_level', 0)
        },
        "houyi": {
            "fn": detect_houyi_shooting_sun,
            "filter": lambda r: r.get('is_houyi'),
            "title": "Houyi Shooting the Sun Results",
            "sort_key": lambda x: x.get('rally_pct', 0)
        },
        "whale": {
            "fn": detect_whale_trading,
            "filter": lambda r: r.get('is_whale'),
            "title": "Whale Trading Alignment Results",
            "sort_key": lambda x: x.get('weekly_momentum', 0)
        }
    }
    
    if pattern not in pattern_map:
        console.print(f"[red]Unknown pattern: {pattern}.[/red]")
        return

    config = pattern_map[pattern]
    console.print("[yellow]Discovering US market tickers...[/yellow]")
    ticker_map = fetch_tickers_with_names()
    all_tickers = sorted(list(ticker_map.keys()))
    
    if limit:
        all_tickers = all_tickers[:limit]
        console.print(f"[yellow]Limiting scan to {limit} tickers.[/yellow]")
    
    console.print(f"[green]Scanning {len(all_tickers)} tickers...[/green]")
    scanner = MarketScanner(all_tickers, ticker_names=ticker_map)
    
    has_fund_filters = any([min_mkt_cap, min_volume, min_score])
    if has_fund_filters:
        with console.status("[bold green]Fetching fundamentals...[/bold green]"):
            scanner.fetch_fundamentals()
            
    with console.status("[bold green]Downloading market data...[/bold green]"):
        scanner.fetch_data(period=period)
        
    with console.status("[bold green]Fetching benchmark (SPY)...[/bold green]"):
        scanner.fetch_benchmark(period=period)
        
    with console.status("[bold green]Analyzing patterns...[/bold green]"):
        mkt_cap_val = min_mkt_cap * 1e9 if min_mkt_cap else None
        bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None
        results = scanner.scan(config['fn'], min_mkt_cap=mkt_cap_val, min_avg_volume=min_volume, min_score=min_score, benchmark_close=bm_close)

    extra_sections = {}
    if pattern == "squeeze":
        with console.status("[bold green]Checking Houyi/Whale matches...[/bold green]"):
            houyi_results = scanner.scan(detect_houyi_shooting_sun, min_mkt_cap=mkt_cap_val, min_avg_volume=min_volume, min_score=min_score, benchmark_close=bm_close)
            whale_results = scanner.scan(detect_whale_trading, min_mkt_cap=mkt_cap_val, min_avg_volume=min_volume, min_score=min_score, benchmark_close=bm_close)
        matched = _attach_pattern_flags([r for r in results if config['filter'](r)], houyi_results, whale_results)

        score_key = "experimental_score" if score_version == "v2" else "ranking_score"
        extra_sections = {
            "houyi": sorted([r for r in houyi_results if r.get("is_houyi")], key=lambda x: x.get("rally_pct", 0), reverse=True),
            "whale": sorted([r for r in whale_results if r.get("is_whale")], key=lambda x: x.get("weekly_momentum", 0), reverse=True),
            "priority": sorted(
                [r for r in matched if r.get(score_key, 0) > 0],
                key=lambda x: (x.get(score_key, 0), x.get("momentum", 0)),
                reverse=True,
            ),
        }

    # --- ETF dual-role: independent scan + regime detection ---
    # ETF results are stored separately and NEVER mixed into stock rankings.
    try:
        from squeeze.data.tickers import get_etf_universe
        etf_universe = get_etf_universe()
        with console.status("[bold green]Scanning ETFs & computing regime...[/bold green]"):
            # Use the same scanner instance: it already has benchmark data.
            # Create a dedicated scanner for the small ETF universe (~16 tickers).
            etf_scanner = MarketScanner(list(etf_universe.keys()), ticker_names=etf_universe)
            etf_scanner.fetch_data(period=period)
            etf_scanner.fetch_benchmark(period=period)
            etf_bm = etf_scanner.benchmark_close if not etf_scanner.benchmark_close.empty else None
            # Regime data (BULLISH/NEUTRAL/BEARISH per ETF)
            regime_data = etf_scanner.fetch_regime_data()
            # Squeeze pattern scan on ETFs (no volume/mktcap filters for ETFs)
            etf_squeeze = etf_scanner.scan(config['fn'], benchmark_close=etf_bm)
            extra_sections["regime_data"] = regime_data
            # Only include ETFs that have an active signal (fired/building/etc.)
            extra_sections["etf_results"] = [r for r in etf_squeeze if config['filter'](r)]
    except Exception as _etf_exc:
        console.print(f"[yellow]Warning: ETF scan skipped: {_etf_exc}[/yellow]")
    # ----------------------------------------------------------


    if min_price is not None:
        results = [r for r in results if r.get('Close', 0) >= min_price]
    if max_price is not None:
        results = [r for r in results if r.get('Close', 0) <= max_price]

    if pattern != "squeeze":
        matched = [r for r in results if config['filter'](r)]
    matched = sorted(matched, key=config['sort_key'], reverse=True)

    # ── Options Skew Confirmation ────────────────────────────────────────
    skew_enriched = None
    if with_options_skew and pattern == "squeeze" and matched:
        console.print(f"[yellow]Running options skew confirmation on top {min(top_n_options, len(matched))} candidates...[/yellow]")
        try:
            from squeeze.data.options_loader import get_expiry_chain
            from squeeze.engine.options_skew import compute_skew
            from squeeze.engine.skew_ranker import attach_skew_to_result

            skew_candidates = matched[:top_n_options]
            skew_enriched = []
            for r in skew_candidates:
                ticker = r["ticker"]
                spot = r.get("Close", 0)
                if not spot or spot <= 0:
                    continue
                chain = get_expiry_chain(ticker)
                if chain is None:
                    continue
                skew_data = compute_skew(chain["calls"], chain["puts"], spot)
                enriched = attach_skew_to_result(r, skew_data)
                skew_enriched.append(enriched)

            if skew_enriched:
                console.print(f"  [green]✔[/green] Options skew computed for {len(skew_enriched)} tickers")
                skew_enriched.sort(key=lambda x: x.get("final_score_v2", 0), reverse=True)

                try:
                    skew_csv_dir = Path("exports") / "skew"
                    skew_csv_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    skew_csv_path = skew_csv_dir / f"squeeze_skew_recommendations_{ts}.csv"

                    skew_cols = [
                        "ticker", "base_signal", "base_score",
                        "squeeze_state", "momentum",
                        "atm_iv", "call_skew", "put_skew",
                        "risk_reversal", "skew_bias",
                        "total_volume", "avg_spread_pct",
                        "otm_call_distance", "otm_put_distance",
                        "liquidity_ok", "iv_overheated",
                        "skew_score_v2",
                        "final_score_v2", "score_delta", "final_action", "reason",
                    ]
                    import csv as csv_module
                    with open(skew_csv_path, "w", newline="", encoding="utf-8") as f:
                        w = csv_module.DictWriter(f, fieldnames=skew_cols, extrasaction="ignore")
                        w.writeheader()
                        w.writerows(skew_enriched)
                    console.print(f"  [green]✔[/green] Skew CSV exported: {skew_csv_path}")

                    table = Table(title=f"Options Skew Confirmation ({len(skew_enriched)} candidates)")
                    table.add_column("Ticker", style="cyan", no_wrap=True)
                    table.add_column("Base", style="bold")
                    table.add_column("Skew Bias", style="magenta")
                    table.add_column("Score", justify="right", style="blue")
                    table.add_column("Delta", justify="right")
                    table.add_column("Final", style="bold")
                    table.add_column("Reason", style="white")

                    confirmed_bullish = []
                    confirmed_bearish = []
                    downgraded = []

                    for e in skew_enriched:
                        delta = e.get("score_delta", 0) or 0
                        final_act = e.get("final_action", "")
                        reason = e.get("reason", "")
                        base_sig = e.get("base_signal", "")
                        skew_bias = e.get("skew_bias", "")

                        if delta > 0:
                            delta_str = f"[green]+{delta:.0f}[/green]"
                        elif delta < 0:
                            delta_str = f"[red]{delta:.0f}[/red]"
                        else:
                            delta_str = "0"

                        table.add_row(
                            e.get("ticker", "?"),
                            base_sig,
                            skew_bias,
                            f"{e.get('final_score_v2', 0):.0f}",
                            delta_str,
                            final_act,
                            reason,
                        )

                        if final_act in ("HIGH_CONVICTION", "BUY_CANDIDATE"):
                            confirmed_bullish.append(e)
                        elif final_act == "DOWNGRADED":
                            downgraded.append(e)
                        elif final_act == "AVOID_OVERHEATED_IV":
                            downgraded.append(e)

                    console.print(table)

                    def _tag_line(items, tag, emoji):
                        if not items:
                            return f"{emoji} {tag}: (none)"
                        names = ", ".join(f"{i['ticker']}{i.get('score_delta',0):+.0f}" for i in items[:5])
                        return f"{emoji} {tag}: {names}"

                    console.print()
                    console.print("[bold]── Options Skew Summary ──[/bold]")
                    console.print(_tag_line(confirmed_bullish, "Skew-confirmed Bullish", "🟢"))
                    console.print(_tag_line(confirmed_bearish, "Skew-confirmed Bearish", "🔴"))
                    console.print(_tag_line(downgraded, "Downgraded by Options Skew", "⚠️"))

                except Exception as csv_err:
                    console.print(f"  [red]✘[/red] Error exporting skew CSV: {csv_err}")
        except Exception as opt_err:
            console.print(f"  [red]✘[/red] Options skew error: {opt_err}")
    
    table = Table(title=f"{config['title']} ({len(matched)} matches)")
    table.add_column("Ticker", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Signal", style="bold")
    
    if pattern == "squeeze":
        table.add_column("Energy", style="yellow")
        table.add_column("Momentum", style="green")
        table.add_column("RS", style="cyan")
        table.add_column("Rank", style="blue")
        table.add_column("Exp", style="magenta")
        for r in matched:
            energy_stars = "★" * r.get('energy_level', 0)
            momentum_color = "green" if r.get('momentum', 0) > 0 else "red"
            ranking = r.get("ranking_score", r.get("composite_score", 0))
            experimental = r.get("experimental_score", r.get("composite_score_v2", 0))
            rs_signal = r.get("rs_signal", "")
            rs_display = rs_signal if rs_signal else ("RS↑" if r.get("rs_slope_5d", 0) > 0 else ("RS↓" if r.get("rs_slope_5d", 0) < 0 else ""))
            table.add_row(r['ticker'], r.get('name', 'Unknown'), r.get('Signal', '觀望'),
                          f"{r['energy_level']} {energy_stars}",
                          f"[{momentum_color}]{r['momentum']:.4f}[/{momentum_color}]",
                          rs_display, str(ranking), str(experimental))
    else:
        table.add_column("Momentum", style="green")
        for r in matched:
            momentum_color = "green" if r.get('momentum', 0) > 0 else "red"
            table.add_row(r['ticker'], r.get('name', 'Unknown'), r.get('Signal', '觀望'), f"[{momentum_color}]{r.get('momentum', 0.0):.4f}[/{momentum_color}]")
    
    console.print(table)
    
    chart_paths = []
    chart_candidates = matched
    if pattern == "squeeze":
        chart_candidates = extra_sections.get("priority", []) or matched

    if export or plot:
        base_dir = output_dir or Path("exports")
        if export:
            console.print("[yellow]Exporting results...[/yellow]")
            exporter = ReportExporter()
            exporter.export(matched, base_dir, extra_sections=extra_sections)
        
        if plot:
            plot_count = min(len(chart_candidates), top)
            console.print(f"[yellow]Generating charts for top {plot_count} picks...[/yellow]")
            exporter = ReportExporter()
            now = exporter._get_market_now()
            charts_dir = base_dir / now.strftime("%Y-%m-%d") / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)
            
            for i in range(plot_count):
                ticker = chart_candidates[i]['ticker']
                try:
                    ticker_data = scanner.data[ticker].dropna(subset=['Close']) if isinstance(scanner.data.columns, pd.MultiIndex) else scanner.data.dropna(subset=['Close'])
                    chart_path = charts_dir / f"{ticker}.png"
                    plot_ticker(ticker_data, ticker, str(chart_path), benchmark_close=bm_close)
                    chart_paths.append(chart_path)
                    console.print(f"  [green]✔[/green] Generated chart for {ticker}")
                except Exception as e:
                    console.print(f"  [red]✘[/red] Error plotting {ticker}: {str(e)}")

    tracking_buys = []
    tracking_sells = []
    try:
        tracker = PerformanceTracker(Path("recommendations.csv"))
        tracker.update_daily_performance()
        tracking_buys = tracker.get_active_tracking_list(rec_type='buy')
        tracking_sells = tracker.get_active_tracking_list(rec_type='sell')
        
        buy_signals = ["強烈買入 (爆發)", "買入 (動能增強)", "觀察 (跌勢收斂)"]
        sell_signals = ["強烈賣出 (跌破)", "賣出 (動能轉弱)"]
        today_buys = [r for r in matched if r.get('Signal') in buy_signals]
        today_sells = [r for r in matched if r.get('Signal') in sell_signals]
        
        market_context = tracker._infer_market_context()
        market_context['pattern'] = pattern
        tracker.record_recommendations(
            today_buys,
            rec_type='buy',
            market_context=market_context,
            stop_loss_pct=tracking_stop_loss_pct,
            stop_loss_ma_window=tracking_stop_loss_ma_window,
            stop_loss_ticks=tracking_stop_loss_ticks,
        )
        tracker.record_recommendations(today_sells, rec_type='sell', market_context=market_context)
    except Exception as e:
        console.print(f"[red]Error during tracking: {str(e)}[/red]")

    if notify:
        console.print("[yellow]Sending notifications...[/yellow]")
        notifier = LineNotifier()
        msg = f"Squeeze Scan Complete (US): {pattern}\nBuy: {len(today_buys)} | Sell: {len(today_sells)}"
        if skew_enriched:
            msg += f"\n\nOptions Skew:\n"
            confirmed = [e for e in skew_enriched if e.get("final_action") in ("HIGH_CONVICTION", "BUY_CANDIDATE")]
            downgraded = [e for e in skew_enriched if e.get("final_action") == "DOWNGRADED"]
            avoided = [e for e in skew_enriched if e.get("final_action") == "AVOID_OVERHEATED_IV"]
            if confirmed:
                msg += "🟢 Confirmed: " + ", ".join(e["ticker"] for e in confirmed[:5]) + "\n"
            if downgraded:
                msg += "⚠️ Downgraded: " + ", ".join(e["ticker"] for e in downgraded[:5]) + "\n"
            if avoided:
                msg += "🔥 Avoid IV: " + ", ".join(e["ticker"] for e in avoided[:5]) + "\n"
        notifier.send_summary(msg)

        email_notifier = EmailNotifier()
        exporter = ReportExporter()
        extra_sections = dict(extra_sections or {})
        if skew_enriched:
            extra_sections["skew"] = skew_enriched
        html_report = exporter.render_html_summary(buy_results=today_buys, sell_results=today_sells, tracking_buys=tracking_buys, tracking_sells=tracking_sells, extra_sections=extra_sections)
        subject = f"Squeeze Scan Report (US - {pattern}) - {pd.Timestamp.now().strftime('%Y-%m-%d')}"
        
        if email_notifier.send_email(subject, html_report, is_html=True, attachments=chart_paths):
            console.print("[green]Email sent successfully with HTML and attachments.[/green]")
        else:
            console.print("[red]Failed to send email.[/red]")


@app.command(name="data-quality")
def data_quality(
    csv_path: Path = typer.Option(Path("recommendations.csv"), "--csv", help="Tracking CSV to analyze."),
):
    """Produce a data quality report for the tracking database."""
    from squeeze.report.performance import normalize_tracking_df

    frame = normalize_tracking_df(pd.read_csv(csv_path)) if csv_path.exists() else pd.DataFrame()
    lines: List[str] = []
    lines.append("# Data Quality Report (US)")
    lines.append(f"Generated: {pd.Timestamp.now(tz='America/New_York').strftime('%Y-%m-%d %H:%M:%S')} EST")
    lines.append("")

    if frame.empty:
        lines.append("**No tracking data found.**")
        report = "\n".join(lines)
        console.print(report)
        return report

    total = len(frame)
    completed = len(frame[frame["status"] == "completed"])
    active = len(frame[frame["status"] == "tracking"])
    lines.append(f"## Overview")
    lines.append(f"- Total records: {total}")
    lines.append(f"- Active: {active}")
    lines.append(f"- Completed: {completed}")
    lines.append(f"- Date range: {frame['date'].min()} to {frame['date'].max()}")

    # Feature coverage
    lines.append("")
    lines.append("## Feature Coverage")
    key_features = ["has_houyi", "has_whale", "close_above_ma20", "ma20_converging",
                     "volume_expansion", "rs_new_high_60", "rs_ratio", "rs_slope_5d",
                     "ranking_score", "experimental_score", "feature_schema_version",
                     "scan_id", "benchmark_last_date"]
    for col in key_features:
        if col in frame.columns:
            non_null = frame[col].notna().sum()
            pct = non_null / total * 100
            lines.append(f"- {col}: {non_null}/{total} ({pct:.1f}%)")
        else:
            lines.append(f"- {col}: column missing")

    # Duplicate check
    lines.append("")
    lines.append("## Duplicate Check")
    if "date" in frame.columns and "ticker" in frame.columns and "type" in frame.columns:
        dups = frame.duplicated(subset=["date", "ticker", "type"]).sum()
        lines.append(f"- Duplicates by (date, ticker, type): {dups}")

    # Daily Trend
    lines.append("")
    lines.append("## Daily Trend")
    if "date" in frame.columns:
        trend = (
            frame.groupby("date")
            .agg(
                tickers=("ticker", "nunique"),
                records=("ticker", "count"),
                rs_cov=("rs_ratio", lambda s: s.notna().mean()),
                bm_fresh=("benchmark_last_date", lambda s: s.dropna().nunique()),
            )
            .reset_index()
            .sort_values("date", ascending=False)
            .head(7)
        )
        if not trend.empty:
            lines.append(f"  {'Date':<12} {'Tickers':>8} {'Records':>8} {'RS%':>6} {'BM_src':>6}")
            for _, row in trend.iterrows():
                lines.append(
                    f"  {str(row['date']):<12} {int(row['tickers']):>8} {int(row['records']):>8} "
                    f"{float(row['rs_cov'])*100:>5.1f}% {int(row['bm_fresh']):>6}"
                )

    report = "\n".join(lines)
    console.print(report)
    return report


@app.command(name="nightly")
def nightly(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Limit tickers (testing only)."),
    period: str = typer.Option("2y", "--period", "-p", help="Data period."),
    tracking_stop_loss_pct: Optional[float] = typer.Option(None, "--tracking-stop-loss-pct"),
    tracking_stop_loss_ma_window: Optional[int] = typer.Option(None, "--tracking-stop-loss-ma-window"),
    tracking_stop_loss_ticks: int = typer.Option(0, "--tracking-stop-loss-ticks"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate pipeline steps without calling external APIs."),
    with_options_skew: bool = typer.Option(True, "--with-options-skew", help="Enable options skew confirmation."),
    top_n_options: int = typer.Option(50, "--top-n-options", help="Number of top squeeze candidates to run options skew on."),
    score_version: str = typer.Option("v1", "--score-version", help="Ranking score version: v1 or v2."),
):
    """
    Nightly research pipeline: scan → tracking update → data quality → analysis → email.
    """
    tz_ny = timezone(timedelta(hours=-5))
    now_ny = datetime.now(tz_ny)
    date_str = now_ny.strftime("%Y-%m-%d")
    time_str = now_ny.strftime("%H:%M:%S")

    console.print(f"[bold cyan]=== Nightly Pipeline {date_str} {time_str} EST ===[/bold cyan]")

    # ---- Step 1: Scan ----
    console.print(f"\n[yellow]Step 1/4: Running squeeze scan...[/yellow]")
    if dry_run:
        console.print("  [grey](dry-run: skipping scan)[/grey]")
        scan_ok = True
        chart_paths = []
    else:
        from squeeze.engine.patterns import detect_squeeze, detect_houyi_shooting_sun, detect_whale_trading
        from squeeze.engine.scanner import MarketScanner
        from squeeze.report.visualizer import plot_ticker

        ticker_map = fetch_tickers_with_names()
        all_tickers = sorted(list(ticker_map.keys()))
        if limit:
            all_tickers = all_tickers[:limit]
            console.print(f"  [yellow]Limited to {limit} tickers.[/yellow]")

        scanner = MarketScanner(all_tickers, ticker_names=ticker_map)
        with console.status("  Fetching fundamentals..."):
            scanner.fetch_fundamentals()
        with console.status("  Downloading market data..."):
            scanner.fetch_data(period=period)
        with console.status("  Fetching benchmark (SPY)..."):
            scanner.fetch_benchmark(period=period)
        with console.status("  Scanning for squeeze pattern..."):
            bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None
            results = scanner.scan(detect_squeeze, benchmark_close=bm_close)
        with console.status("  Checking Houyi/Whale matches..."):
            houyi_results = scanner.scan(detect_houyi_shooting_sun, benchmark_close=bm_close)
            whale_results = scanner.scan(detect_whale_trading, benchmark_close=bm_close)

        matched = _attach_pattern_flags(
            [r for r in results if r.get('is_squeezed') or r.get('fired')],
            houyi_results, whale_results,
        )
        console.print(f"  [green]Done: {len(matched)} matches from {len(results)} scanned[/green]")

        # ── Options Skew Confirmation (for nightly) ───────────────────────
        skew_enriched = []
        if with_options_skew and matched:
            console.print(f"  Running options skew on top {min(top_n_options, len(matched))} candidates...")
            try:
                from squeeze.data.options_loader import get_expiry_chain
                from squeeze.engine.options_skew import compute_skew
                from squeeze.engine.skew_ranker import attach_skew_to_result

                skew_candidates = matched[:top_n_options]
                for r in skew_candidates:
                    ticker = r["ticker"]
                    spot = r.get("Close", 0)
                    if not spot or spot <= 0:
                        continue
                    chain = get_expiry_chain(ticker)
                    if chain is None:
                        continue
                    skew_data = compute_skew(chain["calls"], chain["puts"], spot)
                    enriched = attach_skew_to_result(r, skew_data)
                    skew_enriched.append(enriched)
            except Exception as opt_err:
                console.print(f"  [red]Options skew error in nightly: {opt_err}[/red]")

        score_key = "experimental_score" if score_version == "v2" else "ranking_score"
        extra_sections_data = {
            "houyi": sorted([r for r in houyi_results if r.get("is_houyi")], key=lambda x: x.get("rally_pct", 0), reverse=True),
            "whale": sorted([r for r in whale_results if r.get("is_whale")], key=lambda x: x.get("weekly_momentum", 0), reverse=True),
            "priority": sorted(
                [r for r in matched if r.get(score_key, 0) > 0],
                key=lambda x: (x.get(score_key, 0), x.get("momentum", 0)), reverse=True,
            ),
        }
        if skew_enriched:
            extra_sections_data["skew"] = skew_enriched

        # Export
        exporter = ReportExporter()
        base_dir = Path("exports")
        paths = exporter.export(matched, base_dir, extra_sections=extra_sections_data)
        console.print(f"  [green]Exported: {paths.get('markdown', 'N/A')}[/green]")

        # Generate charts
        top_priority = extra_sections_data["priority"][:10]
        chart_paths = []
        if top_priority:
            charts_dir = base_dir / date_str / "charts"
            charts_dir.mkdir(parents=True, exist_ok=True)
            bm_close = scanner.benchmark_close if not scanner.benchmark_close.empty else None
            for item in top_priority:
                ticker = item["ticker"]
                try:
                    ticker_data = scanner.data[ticker].dropna(subset=['Close']) if isinstance(scanner.data.columns, pd.MultiIndex) else scanner.data.dropna(subset=['Close'])
                    chart_path = charts_dir / f"{ticker}.png"
                    plot_ticker(ticker_data, ticker, str(chart_path), benchmark_close=bm_close)
                    chart_paths.append(chart_path)
                except Exception as e:
                    console.print(f"  [red]Chart error {ticker}: {e}[/red]")
            console.print(f"  [green]Charts: {len(chart_paths)} generated[/green]")

        # Tracking
        tracker = PerformanceTracker(Path("recommendations.csv"))
        tracker.update_daily_performance()
        market_context = tracker._infer_market_context()
        market_context['pattern'] = 'squeeze'
        buy_signals = ["強烈買入 (爆發)", "買入 (動能增強)", "觀察 (跌勢收斂)"]
        sell_signals = ["強烈賣出 (跌破)", "賣出 (動能轉弱)"]
        today_buys = [r for r in matched if r.get('Signal') in buy_signals]
        today_sells = [r for r in matched if r.get('Signal') in sell_signals]
        tracker.record_recommendations(
            today_buys, rec_type='buy', market_context=market_context,
            stop_loss_pct=tracking_stop_loss_pct,
            stop_loss_ma_window=tracking_stop_loss_ma_window,
            stop_loss_ticks=tracking_stop_loss_ticks,
        )
        tracker.record_recommendations(today_sells, rec_type='sell', market_context=market_context)
        tracking_buys = tracker.get_active_tracking_list(rec_type='buy')
        tracking_sells = tracker.get_active_tracking_list(rec_type='sell')

    # ---- Step 2: Data quality ----
    console.print(f"\n[yellow]Step 2/4: Data quality report...[/yellow]")
    dq_report = data_quality(csv_path=Path("recommendations.csv"))
    dq_path = Path("exports") / date_str / f"data-quality_{time_str.replace(':','')}.md"
    dq_path.parent.mkdir(parents=True, exist_ok=True)
    dq_path.write_text(dq_report or "# Data Quality Report\nNo data.")
    console.print(f"  [green]Saved: {dq_path}[/green]")

    # ---- Step 3: Tracking analysis ----
    console.print(f"\n[yellow]Step 3/4: Tracking analysis report...[/yellow]")
    if Path("recommendations.csv").exists():
        frame = load_tracking_frame("recommendations.csv")
        report = build_tracking_report(frame)
        text = format_tracking_report(report)
        analysis_path = Path("exports") / date_str / f"tracking-analysis_{time_str.replace(':','')}.md"
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(text)
        console.print(f"  [green]Saved: {analysis_path}[/green]")
    else:
        text = "No tracking data yet."
        analysis_path = None
        console.print("  [yellow]No recommendations.csv found, skipping analysis.[/yellow]")

    # ---- Step 4: Notify ----
    console.print(f"\n[yellow]Step 4/4: Sending email notification...[/yellow]")
    if not dry_run:
        email_notifier = EmailNotifier()
        exporter = ReportExporter()
        html = exporter.render_html_summary(
            buy_results=today_buys if not dry_run else [],
            sell_results=today_sells if not dry_run else [],
            tracking_buys=tracking_buys if not dry_run else [],
            tracking_sells=tracking_sells if not dry_run else [],
            extra_sections=extra_sections_data,
        )
        attachments = [p for p in [dq_path, analysis_path] if p and p.exists()]
        if not dry_run:
            attachments += [p for p in chart_paths if p.exists()]
        subject = f"Squeeze Nightly Report (US) {date_str}"
        email_notifier.send_email(subject, html, is_html=True, attachments=attachments)
        console.print("  [green]Email sent.[/green]")
    else:
        console.print("  [grey](dry-run: skipping notification)[/grey]")

    console.print(f"\n[bold cyan]=== Nightly Pipeline Complete ({date_str}) ===[/bold cyan]")


if __name__ == "__main__":
    app()
