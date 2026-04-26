"""Unit tests for options skew calculation and data loading."""

import pandas as pd
import pytest

from squeeze.data.options_loader import select_nearest_expiry, filter_liquid_options, MIN_OPEN_INTEREST
from squeeze.engine.options_skew import (
    resolve_atm_strike,
    resolve_otm_strikes,
    compute_skew,
)
from squeeze.engine.skew_ranker import compute_skew_score_for_result, attach_skew_to_result
from unittest.mock import patch, MagicMock


# ── helpers ────────────────────────────────────────────────────────────

def _make_option_df(strikes, ivs, ois=None):
    """Build a yfinance-style option chain DataFrame."""
    data = {"strike": strikes, "impliedVolatility": ivs, "openInterest": ois or [100] * len(strikes)}
    return pd.DataFrame(data)


# ── options_loader ─────────────────────────────────────────────────────

class TestSelectNearestExpiry:
    def test_in_window(self):
        dates = ["2026-05-01", "2026-05-15", "2026-05-29", "2026-06-12"]
        ref = pd.Timestamp("2026-04-26")
        got = select_nearest_expiry(dates, min_dte=21, max_dte=45, ref_date=ref)
        # 2026-05-29 = 33 DTE — inside window and closest to 21
        assert got == "2026-05-29"

    def test_fall_back_above_min(self):
        dates = ["2026-05-01", "2026-05-08"]  # 5, 12 DTE
        ref = pd.Timestamp("2026-04-26")
        got = select_nearest_expiry(dates, min_dte=21, max_dte=45, ref_date=ref)
        # Should return the farthest available (still below min, but closest)
        assert got == "2026-05-08"

    def test_empty_dates(self):
        assert select_nearest_expiry([], ref_date=pd.Timestamp("2026-04-26")) is None


class TestFilterLiquidOptions:
    def test_filters_below_min_oi(self):
        df = _make_option_df(
            strikes=[100, 105, 110],
            ivs=[0.25, 0.26, 0.27],
            ois=[10, 100, 200],  # First row has OI 10 < 50
        )
        filtered = filter_liquid_options(df, min_oi=MIN_OPEN_INTEREST)
        assert len(filtered) == 2
        assert all(filtered["openInterest"] >= MIN_OPEN_INTEREST)

    def test_empty_df(self):
        assert filter_liquid_options(pd.DataFrame(), min_oi=50).empty


# ── options_skew ───────────────────────────────────────────────────────

class TestResolveAtmStrike:
    def test_basic(self):
        calls = _make_option_df([100, 105, 110], [0.2, 0.22, 0.25])
        puts = _make_option_df([95, 100, 105], [0.25, 0.22, 0.2])
        atm = resolve_atm_strike(calls, puts, spot=102)
        assert atm == 100  # closest to 102

    def test_empty_chains(self):
        atm = resolve_atm_strike(pd.DataFrame(), pd.DataFrame(), spot=100)
        assert atm == 100  # falls back to spot


class TestResolveOtmStrikes:
    def test_basic(self):
        calls = _make_option_df([100, 105, 110], [0.2, 0.22, 0.25])
        puts = _make_option_df([95, 100, 105], [0.25, 0.22, 0.2])
        otm_call, otm_put = resolve_otm_strikes(calls, puts, spot=102, atm_strike=100)
        assert otm_call == 105   # first strike above 100
        assert otm_put == 95     # first strike below 100


class TestComputeSkew:
    def test_bullish_skew(self):
        """Bullish scenario: OTM calls more expensive than OTM puts."""
        calls = _make_option_df([95, 100, 105], [0.30, 0.25, 0.28])
        puts = _make_option_df([90, 95, 100], [0.35, 0.32, 0.25])
        result = compute_skew(calls, puts, spot=98)

        assert result["spot"] == 98
        assert result["atm_strike"] == 100
        assert result["atm_iv"] == 0.25
        assert result["otm_call_strike"] == 105
        assert result["otm_put_strike"] == 95
        assert result["otm_call_iv"] == 0.28
        assert result["otm_put_iv"] == 0.32
        # risk_reversal = 0.28 - 0.32 = -0.04 → bearish
        assert result["risk_reversal"] == pytest.approx(-0.04, abs=1e-6)
        assert result["skew_bias"] == "bearish"
        assert result["skew_score"] < 0

    def test_bearish_skew(self):
        """Bearish scenario: OTM puts more expensive than OTM calls."""
        calls = _make_option_df([95, 100, 105], [0.30, 0.25, 0.28])
        puts = _make_option_df([90, 95, 100], [0.35, 0.32, 0.25])
        # Same data as above → bearish (puts more expensive)
        result = compute_skew(calls, puts, spot=98)
        assert result["skew_bias"] == "bearish"
        assert result["skew_score"] < 0

    def test_neutral_skew(self):
        calls = _make_option_df([95, 100, 105], [0.30, 0.25, 0.255])
        puts = _make_option_df([90, 95, 100], [0.255, 0.25, 0.25])
        result = compute_skew(calls, puts, spot=98)
        assert result["skew_bias"] == "neutral"

    def test_empty_chains(self):
        result = compute_skew(pd.DataFrame(), pd.DataFrame(), spot=100)
        assert result["atm_iv"] is None
        assert result["skew_bias"] == "neutral"


# ── skew_ranker ────────────────────────────────────────────────────────

class TestSkewRanker:
    def test_compute_score(self):
        result = {"composite_score": 5}
        skew_data = {"skew_score": 0.5}
        score = compute_skew_score_for_result(result, skew_data)
        assert score == 5.5

    def test_attach_skew(self):
        result = {"ticker": "AAPL", "Signal": "強烈買入 (爆發)", "composite_score": 3}
        skew_data = {
            "spot": 150,
            "atm_iv": 0.25,
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["ticker"] == "AAPL"
        assert enriched["Signal"] == "強烈買入 (爆發)"  # unchanged
        assert enriched["atm_iv"] == 0.25
        assert enriched["call_skew"] == 0.03
        assert enriched["skew_bias"] == "bullish"
        assert enriched["final_score_v2"] == 3.5

    def test_signal_unchanged(self):
        """The original Signal field must never be altered."""
        result = {"ticker": "MSFT", "Signal": "觀望 (動能減弱)", "composite_score": 1}
        skew_data = {"skew_score": 0.8, "skew_bias": "bullish"}
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["Signal"] == "觀望 (動能減弱)"


class TestGetExpiryChain:
    """Tests for get_expiry_chain using mocked yfinance."""

    @patch("squeeze.data.options_loader.yf.Ticker")
    def test_returns_expected_contract(self, mock_ticker_cls):
        from squeeze.data.options_loader import get_expiry_chain

        mock_ticker = MagicMock()
        mock_ticker_cls.return_value = mock_ticker
        mock_ticker.options = ["2026-05-15", "2026-05-29", "2026-06-12"]

        # Build mock option chain DataFrames
        mock_calls = _make_option_df([95, 100, 105], [0.25, 0.26, 0.27])
        mock_puts = _make_option_df([95, 100, 105], [0.28, 0.26, 0.24])
        mock_chain = MagicMock()
        mock_chain.calls = mock_calls
        mock_chain.puts = mock_puts
        mock_ticker.option_chain.return_value = mock_chain

        ref_date = pd.Timestamp("2026-04-26")
        result = get_expiry_chain("AAPL", min_dte=21, max_dte=45, ref_date=ref_date)

        assert result is not None
        # 2026-05-29 = 33 DTE, should be selected
        assert result["expiry"] == "2026-05-29"
        assert "calls" in result
        assert "puts" in result
        assert not result["calls"].empty
        assert not result["puts"].empty
        assert list(result["calls"].columns) == ["strike", "impliedVolatility", "openInterest"]

    @patch("squeeze.data.options_loader.yf.Ticker")
    def test_returns_none_on_failure(self, mock_ticker_cls):
        from squeeze.data.options_loader import get_expiry_chain

        mock_ticker = MagicMock()
        mock_ticker_cls.return_value = mock_ticker
        mock_ticker.options = []  # No expirations

        result = get_expiry_chain("AAPL")
        assert result is None
