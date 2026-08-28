# Updated with benchmark fetching and score enrichment from Taiwan screener
import logging
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from typing import Callable, List, Dict, Any, Optional
import numpy as np
import yfinance as yf
from squeeze.data.downloader import download_market_data
from squeeze.data.fundamentals import get_fundamentals
from squeeze.engine.ranker import calculate_value_score, enrich_with_scores

SPY_TICKER = "SPY"

# Configure logging
logger = logging.getLogger(__name__)

class MarketScanner:
    """
    MarketScanner handles high-performance market-wide scanning for patterns.
    Uses a hybrid approach:
    - Threading for I/O bound data fetching (via yfinance).
    - Multiprocessing for CPU bound pattern detection.
    """
    
    def __init__(self, tickers: List[str], ticker_names: Optional[Dict[str, str]] = None):
        """
        Initialize the scanner with a list of tickers.
        
        Args:
            tickers: List of ticker strings (e.g., ["AAPL", "MSFT"]).
            ticker_names: Optional dictionary mapping ticker to company name.
        """
        self.tickers = tickers
        self.ticker_names = ticker_names or {}
        self.data: pd.DataFrame = pd.DataFrame()
        self.fundamentals: pd.DataFrame = pd.DataFrame()
        self.benchmark_close: pd.Series = pd.Series(dtype=float)
        self.benchmark_metadata: Dict[str, Any] = {
            "benchmark_symbol": SPY_TICKER,
            "benchmark_source": "yfinance",
        }
        self._scan_id: str = ""
        self.results: List[Dict[str, Any]] = []

    def fetch_data(self, period: str = "2y", data: pd.DataFrame = None):
        """
        Fetch market data for all tickers or use provided data.
        """
        if data is not None:
            self.data = data
            return self.data
            
        logger.info(f"Fetching data for {len(self.tickers)} tickers...")
        self.data = download_market_data(self.tickers, period=period)
        return self.data

    def fetch_benchmark(self, period: str = "2y", ticker: str = SPY_TICKER) -> pd.Series:
        """Fetch benchmark (SPY) close prices for RS calculation."""
        logger.info(f"Fetching benchmark {ticker}...")
        self.benchmark_metadata["benchmark_period"] = period
        try:
            bm_df = yf.download(ticker, period=period, interval="1d", progress=False)
            if bm_df is not None and not bm_df.empty:
                if "Close" in bm_df.columns:
                    self.benchmark_close = bm_df["Close"].squeeze()
                elif "Adj Close" in bm_df.columns:
                    self.benchmark_close = bm_df["Adj Close"].squeeze()
                # Record the last available benchmark date
                if isinstance(self.benchmark_close, pd.Series) and not self.benchmark_close.empty:
                    self.benchmark_metadata["benchmark_last_date"] = str(self.benchmark_close.index[-1].date())
        except Exception as e:
            logger.warning(f"Failed to fetch benchmark {ticker}: {e}")
        return self.benchmark_close

    def fetch_regime_data(self) -> dict:
        """
        Fetch market/sector regime context using MARKET_ETFS + SECTOR_ETFS.

        Downloads 1 year of daily OHLCV for all ETFs in get_etf_universe() and
        computes per-ETF: 20-day MA, 50-day MA, 14-day RSI, and 20-day momentum.

        Regime classification:
          BULLISH  — price above both MAs AND 20d momentum > 0
          BEARISH  — price below both MAs AND 20d momentum < 0
          NEUTRAL  — anything in between

        Returns:
            Dict[ticker, {name, above_20ma, above_50ma, rsi_14, momentum_20d, regime}]
            Returns {} on total download failure (fail-safe, no hard crash).
        """
        from squeeze.data.tickers import get_etf_universe
        etf_universe = get_etf_universe()
        etfs = list(etf_universe.keys())
        logger.info(f"Fetching regime data for {len(etfs)} ETFs: {etfs}")

        try:
            # Download all ETFs in one batch for speed (~16 tickers)
            raw = yf.download(etfs, period="1y", interval="1d", group_by="ticker",
                              auto_adjust=True, progress=False, threads=True)
        except Exception as exc:
            logger.error(f"ETF regime batch download failed: {exc}")
            return {}

        regime_data: dict = {}
        for ticker in etfs:
            try:
                # Handle MultiIndex (multiple tickers) vs flat (single ticker)
                if isinstance(raw.columns, pd.MultiIndex):
                    if ticker not in raw.columns.get_level_values(0):
                        continue
                    tdf = raw[ticker].dropna(subset=["Close"])
                else:
                    tdf = raw.dropna(subset=["Close"])

                if tdf.empty or len(tdf) < 50:
                    continue

                close = tdf["Close"]
                last  = float(close.iloc[-1])
                ma20  = float(close.rolling(20).mean().iloc[-1])
                ma50  = float(close.rolling(50).mean().iloc[-1])

                above_20ma = last > ma20
                above_50ma = last > ma50

                # 20-day price momentum (% change)
                momentum_20d = float((last / close.iloc[-21]) - 1) if len(close) > 20 else 0.0

                # RSI-14
                delta = close.diff()
                gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
                loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
                rs    = gain / loss.replace(0, float("nan"))
                rsi_14 = float((100 - (100 / (1 + rs))).iloc[-1])

                # Regime classification
                if above_20ma and above_50ma and momentum_20d > 0:
                    regime = "BULLISH"
                elif not above_20ma and not above_50ma and momentum_20d < 0:
                    regime = "BEARISH"
                else:
                    regime = "NEUTRAL"

                regime_data[ticker] = {
                    "name":        etf_universe.get(ticker, ticker),
                    "above_20ma":  above_20ma,
                    "above_50ma":  above_50ma,
                    "rsi_14":      rsi_14,
                    "momentum_20d": momentum_20d,
                    "regime":      regime,
                }
            except Exception as exc:
                logger.warning(f"Regime calc failed for {ticker}: {exc}")
                continue

        logger.info(
            "Regime summary: %s",
            {t: d["regime"] for t, d in regime_data.items()}
        )
        return regime_data



    def fetch_fundamentals(self):
        """
        Fetch fundamental data for all tickers and calculate Value Score.
        """
        logger.info(f"Fetching fundamentals for {len(self.tickers)} tickers...")
        raw_fundamentals = get_fundamentals(self.tickers)
        if not raw_fundamentals.empty:
            self.fundamentals = calculate_value_score(raw_fundamentals)
        return self.fundamentals

    def scan(self, 
              pattern_fn: Callable[[pd.DataFrame], Dict[str, Any]], 
              min_mkt_cap: Optional[float] = None,
              min_avg_volume: Optional[float] = None,
              min_score: Optional[float] = None,
              benchmark_close: Optional[pd.Series] = None) -> List[Dict[str, Any]]:
        """
        Scan the downloaded market data for a given pattern and apply fundamental filters.
        """
        if self.data.empty:
            logger.warning("No data to scan. Call fetch_data() first.")
            return []

        # 1. Apply fundamental filters first if data is available
        filtered_tickers = self.tickers
        fundamental_map = {}
        
        if not self.fundamentals.empty:
            df_fund = self.fundamentals.copy()
            
            # Apply filters
            if min_mkt_cap is not None:
                df_fund = df_fund[df_fund['marketCap'] >= min_mkt_cap]
            if min_avg_volume is not None:
                df_fund = df_fund[df_fund['averageVolume'] >= min_avg_volume]
            if min_score is not None:
                df_fund = df_fund[df_fund['value_score'] >= min_score]
                
            filtered_tickers = df_fund['ticker'].tolist()
            # Create a map for easy lookup later
            fundamental_map = df_fund.set_index('ticker').to_dict('index')
            logger.info(f"Fundamental filtering reduced tickers from {len(self.tickers)} to {len(filtered_tickers)}")

        # 2. Prepare ticker tasks
        tasks = []
        if len(self.tickers) == 1:
            ticker = self.tickers[0]
            if ticker in filtered_tickers and not self.data.empty:
                tasks.append((ticker, self.data))
        else:
            for ticker in filtered_tickers:
                try:
                    if ticker in self.data.columns.levels[0]:
                        ticker_df = self.data[ticker].dropna(subset=['Close'])
                        if not ticker_df.empty:
                            tasks.append((ticker, ticker_df))
                except (KeyError, AttributeError):
                    continue

        if not tasks:
            logger.warning("No valid ticker data found to scan after filtering.")
            return []

        # 3. Pattern Detection (Multiprocessing)
        results = []
        # Generate a stable scan_id for this batch
        from datetime import datetime
        self._scan_id = datetime.now().strftime("scan_%Y%m%d_%H%M%S")
        # Bind benchmark_close to pattern_fn if available (partial is picklable)
        if benchmark_close is not None and not benchmark_close.empty:
            wrapped_fn = partial(pattern_fn, benchmark_close=benchmark_close)
        else:
            wrapped_fn = pattern_fn

        with ProcessPoolExecutor() as executor:
            future_to_ticker = {executor.submit(wrapped_fn, df): ticker for ticker, df in tasks}
            
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    result = future.result()
                    result['ticker'] = ticker
                    result['name'] = self.ticker_names.get(ticker, "未知")
                    
                    # Merge fundamental data into results
                    if ticker in fundamental_map:
                        result.update(fundamental_map[ticker])
                        
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error scanning ticker {ticker}: {str(e)}")
                    results.append({
                        'ticker': ticker,
                        'name': self.ticker_names.get(ticker, "未知"),
                        'error': str(e),
                        'is_squeezed': False
                    })
        
        self.results = enrich_with_scores(results)
        # Attach benchmark metadata + scan_id to each result
        for r in self.results:
            r.update(self.benchmark_metadata)
            r["scan_id"] = self._scan_id
        return self.results
