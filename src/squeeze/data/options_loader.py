"""
Options chain data loader using yfinance.

Fetches US equity option chains and selects the nearest expiration
within a configured DTE window (default 21-45 days).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# Minimum open interest to consider a contract liquid enough for skew calculation.
MIN_OPEN_INTEREST = 50
# Target DTE range for selecting the "front month" expiration.
MIN_DTE = 21
MAX_DTE = 45


def get_option_chain(ticker: str) -> Optional[dict]:
    """
    Fetch the full option chain for *ticker* and return a dict with two keys
    ``calls`` / ``puts``, each holding a DataFrame as returned by yfinance.

    Returns ``None`` if the ticker has no chain or the request fails.
    """
    try:
        stock = yf.Ticker(ticker)
        chain = stock.option_chain()
        return {
            "calls": chain.calls,
            "puts": chain.puts,
        }
    except Exception:
        logger.warning("Failed to fetch option chain for %s", ticker, exc_info=True)
        return None


def get_option_chain_dates(ticker: str) -> list[str]:
    """
    Return all available expiration dates (as 'YYYY-MM-DD' strings) for *ticker*.
    """
    try:
        stock = yf.Ticker(ticker)
        return stock.options
    except Exception:
        logger.warning("Failed to list option dates for %s", ticker, exc_info=True)
        return []


def select_nearest_expiry(
    dates: list[str],
    min_dte: int = MIN_DTE,
    max_dte: int = MAX_DTE,
    ref_date: Optional[datetime] = None,
) -> Optional[str]:
    """
    From a list of expiration date strings, pick the one closest to
    ``min_dte`` days out that still falls inside the ``[min_dte, max_dte]``
    window.

    If none fall inside the window, returns the closest expiry above
    ``min_dte`` (preferring the earliest available date).
    """
    if not dates:
        return None

    ref = ref_date or datetime.now()
    parsed = []
    for d in dates:
        try:
            exp = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        dte = (exp - ref).days
        parsed.append((dte, d))

    # 1. Prefer expiry inside the window closest to min_dte.
    in_window = [(dte, d) for dte, d in parsed if min_dte <= dte <= max_dte]
    if in_window:
        # Pick the closest to min_dte
        in_window.sort(key=lambda x: x[0])
        return in_window[0][1]

    # 2. Fallback: earliest expiry that meets min_dte.
    above_min = [(dte, d) for dte, d in parsed if dte >= min_dte]
    if above_min:
        above_min.sort(key=lambda x: x[0])
        return above_min[0][1]

    # 3. Last resort: the farthest available date.
    parsed.sort(key=lambda x: x[0], reverse=True)
    return parsed[0][1]


def filter_liquid_options(df, min_oi: int = MIN_OPEN_INTEREST) -> "pd.DataFrame":
    """
    Return only rows with ``openInterest >= min_oi``.
    Accepts calls or puts DataFrame as returned by yfinance.
    """
    import pandas as pd

    if df is None or df.empty:
        return pd.DataFrame()

    return df[df.get("openInterest", 0) >= min_oi].copy()


def get_expiry_chain(
    ticker: str,
    min_dte: int = MIN_DTE,
    max_dte: int = MAX_DTE,
    min_oi: int = MIN_OPEN_INTEREST,
    ref_date: Optional[datetime] = None,
) -> Optional[dict]:
    """
    High-level helper:

    1. List available expirations.
    2. Pick the nearest one inside the DTE window.
    3. Fetch the full chain for that expiry.
    4. Filter to liquid contracts.

    Returns ``{"calls": DataFrame, "puts": DataFrame}`` or ``None``.
    """
    try:
        stock = yf.Ticker(ticker)
        dates = stock.options
    except Exception:
        logger.warning("Failed to list options for %s", ticker, exc_info=True)
        return None

    expiry = select_nearest_expiry(dates, min_dte=min_dte, max_dte=max_dte, ref_date=ref_date)
    if expiry is None:
        logger.debug("No suitable expiry found for %s", ticker)
        return None

    try:
        chain = stock.option_chain(expiry)
    except Exception:
        logger.warning("Failed to fetch chain for %s @ %s", ticker, expiry, exc_info=True)
        return None

    return {
        "expiry": expiry,
        "calls": filter_liquid_options(chain.calls, min_oi=min_oi),
        "puts": filter_liquid_options(chain.puts, min_oi=min_oi),
    }
