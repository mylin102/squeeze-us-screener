"""
Options skew calculation engine.

Computes ATM / OTM implied volatilities and derived skew metrics
from a yfinance option chain DataFrame.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default moneyness thresholds for selecting OTM strikes.
OTM_CALL_DELTA_TARGET = 0.25  # ~25 delta call
OTM_PUT_DELTA_TARGET = -0.25  # ~25 delta put


def _nearest_strike(target: float, strikes: pd.Series) -> float:
    """Return the strike closest to *target*."""
    idx = (strikes - target).abs().idxmin()
    return strikes.loc[idx]


def resolve_atm_strike(calls: pd.DataFrame, puts: pd.DataFrame, spot: float) -> float:
    """
    Determine the ATM strike closest to *spot*.
    Uses whichever chain (calls or puts) has a strike close to spot.
    """
    series_list = []
    cs = calls.get("strike", pd.Series(dtype=float))
    if not cs.empty:
        series_list.append(cs)
    ps = puts.get("strike", pd.Series(dtype=float))
    if not ps.empty:
        series_list.append(ps)
    if not series_list:
        logger.warning("No strikes available; falling back to spot")
        return spot
    all_strikes = pd.concat(series_list).dropna().unique()
    return _nearest_strike(spot, pd.Series(all_strikes))


def resolve_otm_strikes(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    spot: float,
    atm_strike: float,
) -> tuple[float, float]:
    """
    Return ``(otm_call_strike, otm_put_strike)``.

    OTM call: the strike just above the ATM strike (calls with strike > atm).
    OTM put : the strike just below the ATM strike (puts with strike < atm).
    """
    call_strikes = calls.get("strike", pd.Series(dtype=float)).dropna()
    put_strikes = puts.get("strike", pd.Series(dtype=float)).dropna()

    otm_call = call_strikes[call_strikes > atm_strike].min()
    otm_put = put_strikes[put_strikes < atm_strike].max()

    # If one side is missing, fall back to the next available strike from either chain.
    if pd.isna(otm_call):
        above_parts = []
        above_calls = call_strikes[call_strikes > atm_strike]
        if not above_calls.empty:
            above_parts.append(above_calls)
        above_puts = put_strikes[put_strikes > atm_strike]
        if not above_puts.empty:
            above_parts.append(above_puts)
        otm_call = pd.concat(above_parts).min() if above_parts else spot * 1.1

    if pd.isna(otm_put):
        below_parts = []
        below_calls = call_strikes[call_strikes < atm_strike]
        if not below_calls.empty:
            below_parts.append(below_calls)
        below_puts = put_strikes[put_strikes < atm_strike]
        if not below_puts.empty:
            below_parts.append(below_puts)
        otm_put = pd.concat(below_parts).max() if below_parts else spot * 0.9

    return float(otm_call), float(otm_put)


def _iv_for_strike(df: pd.DataFrame, strike: float) -> Optional[float]:
    """
    Return the ``impliedVolatility`` for the row whose strike is closest
    to *strike*.  Returns ``None`` if the DataFrame is empty.
    """
    if df.empty:
        return None
    match = df.iloc[(df["strike"] - strike).abs().idxmin()]
    iv = match.get("impliedVolatility")
    return float(iv) if pd.notna(iv) else None


def compute_skew(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    spot: float,
) -> dict:
    """
    Compute skew metrics from call/put DataFrames and the current spot price.

    Returns a dict with keys:
        spot, atm_strike, atm_iv, otm_call_strike, otm_call_iv,
        otm_put_strike, otm_put_iv, call_skew, put_skew,
        risk_reversal, total_skew, skew_bias, skew_score,
        total_volume, avg_spread_pct,
        otm_call_distance, otm_put_distance
    """
    result: dict = {
        "spot": spot,
        "atm_strike": None,
        "atm_iv": None,
        "otm_call_strike": None,
        "otm_call_iv": None,
        "otm_put_strike": None,
        "otm_put_iv": None,
        "call_skew": None,
        "put_skew": None,
        "risk_reversal": None,
        "total_skew": None,
        "skew_bias": "neutral",
        "skew_score": 0.0,
        "total_volume": 0.0,
        "avg_spread_pct": None,
        "otm_call_distance": None,
        "otm_put_distance": None,
    }

    if calls.empty and puts.empty:
        logger.warning("Both call and put chains are empty")
        return result

    atm_strike = resolve_atm_strike(calls, puts, spot)
    result["atm_strike"] = atm_strike

    atm_iv = _iv_for_strike(calls, atm_strike) or _iv_for_strike(puts, atm_strike)
    result["atm_iv"] = atm_iv

    otm_call_strike, otm_put_strike = resolve_otm_strikes(calls, puts, spot, atm_strike)
    result["otm_call_strike"] = otm_call_strike
    result["otm_put_strike"] = otm_put_strike

    # -- OTM strike distance (proportion of spot) --
    result["otm_call_distance"] = round(abs(otm_call_strike - atm_strike) / spot, 4)
    result["otm_put_distance"] = round(abs(otm_put_strike - atm_strike) / spot, 4)

    otm_call_iv = _iv_for_strike(calls, otm_call_strike) or _iv_for_strike(puts, otm_call_strike)
    otm_put_iv = _iv_for_strike(puts, otm_put_strike) or _iv_for_strike(calls, otm_put_strike)
    result["otm_call_iv"] = otm_call_iv
    result["otm_put_iv"] = otm_put_iv

    # -- liquidity estimation (volume + spread) --
    # Aggregate volume from ATM and OTM contracts
    total_vol = 0.0
    bid_prices = []
    ask_prices = []
    for key_df, key_strike in [("calls", atm_strike), ("puts", atm_strike),
                                ("calls", otm_call_strike), ("puts", otm_put_strike)]:
        df_ref = calls if key_df == "calls" else puts
        match = df_ref.loc[df_ref["strike"] == key_strike] if not df_ref.empty else pd.DataFrame()
        if not match.empty:
            row = match.iloc[0]
            vol = row.get("volume")
            if pd.notna(vol):
                total_vol += float(vol)
            bid = row.get("bid")
            ask = row.get("ask")
            if pd.notna(bid) and pd.notna(ask) and float(bid) > 0:
                bid_prices.append(float(bid))
                ask_prices.append(float(ask))

    result["total_volume"] = total_vol
    if bid_prices and ask_prices:
        avg_spread_pct = sum((a - b) / b for a, b in zip(ask_prices, bid_prices)) / len(bid_prices)
        result["avg_spread_pct"] = round(avg_spread_pct, 4)
    else:
        result["avg_spread_pct"] = None

    # -- compute derived metrics --
    if atm_iv is not None and otm_call_iv is not None:
        result["call_skew"] = round(otm_call_iv - atm_iv, 6)

    if atm_iv is not None and otm_put_iv is not None:
        result["put_skew"] = round(otm_put_iv - atm_iv, 6)

    if otm_call_iv is not None and otm_put_iv is not None:
        result["risk_reversal"] = round(otm_call_iv - otm_put_iv, 6)

    # Total skew magnitude (for scoring)
    cs = result.get("call_skew")
    ps = result.get("put_skew")
    if cs is not None and ps is not None:
        result["total_skew"] = round(cs - ps, 6)

    # -- human-readable bias --
    rr = result.get("risk_reversal")
    if rr is not None:
        if rr > 0.02:
            result["skew_bias"] = "bullish"        # calls expensive → bullish sentiment
        elif rr < -0.02:
            result["skew_bias"] = "bearish"         # puts expensive → bearish sentiment
        else:
            result["skew_bias"] = "neutral"

        # Numeric score: positive = bullish skew, negative = bearish skew
        # Clamp to [-1, 1]
        result["skew_score"] = round(np.clip(rr * 10, -1.0, 1.0), 4)

    return result


def compute_skew_for_ticker(
    ticker: str,
    spot: float,
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
) -> dict:
    """
    Convenience wrapper: call ``compute_skew`` and attach the ticker.

    Returns the same dict as ``compute_skew`` plus a ``ticker`` key.
    """
    skew = compute_skew(calls_df, puts_df, spot)
    skew["ticker"] = ticker
    return skew
