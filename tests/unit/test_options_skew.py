"""Unit tests for options skew calculation and data loading."""

import pandas as pd
import pytest

from squeeze.data.options_loader import select_nearest_expiry, filter_liquid_options, MIN_OPEN_INTEREST
from squeeze.engine.options_skew import (
    resolve_atm_strike,
    resolve_otm_strikes,
    compute_skew,
)
from squeeze.engine.skew_ranker import (
    translate_base_signal,
    compute_skew_offset,
    compute_final_score_v2,
    determine_final_action,
    determine_reason,
    attach_skew_to_result,
)
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

class TestTranslateBaseSignal:
    def test_strong_buy(self):
        assert translate_base_signal("強烈買入 (爆發)") == "STRONG_BUY"

    def test_buy(self):
        assert translate_base_signal("買入 (動能增強)") == "BUY"

    def test_watch_converge(self):
        assert translate_base_signal("觀察 (跌勢收斂)") == "WATCH_CONVERGE"

    def test_sell(self):
        assert translate_base_signal("賣出 (動能轉弱)") == "SELL"

    def test_unknown_pass_through(self):
        assert translate_base_signal("SOMETHING") == "SOMETHING"


class TestComputeSkewOffset:
    def test_bullish_confirmed(self):
        """STRONG_BUY + risk_reversal > 0 + call_skew > 0 → +10"""
        offset = compute_skew_offset("強烈買入 (爆發)", 0.05, 0.03, -0.02)
        assert offset == 10

    def test_bullish_contradicted(self):
        """BUY + put_skew > call_skew → -10"""
        offset = compute_skew_offset("買入 (動能增強)", 0.01, 0.01, 0.05)
        assert offset == -10

    def test_bullish_neutral(self):
        """BUY + balanced skew (no clear confirm or contradict) → 0"""
        offset = compute_skew_offset("買入 (動能增強)", 0.0, 0.0, 0.0)
        assert offset == 0

    def test_bearish_confirmed(self):
        """STRONG_SELL + risk_reversal < 0 + put_skew > 0 → +10"""
        offset = compute_skew_offset("強烈賣出 (跌破)", -0.04, -0.01, 0.03)
        assert offset == 10

    def test_bearish_contradicted(self):
        """SELL + call_skew > put_skew → -10"""
        offset = compute_skew_offset("賣出 (動能轉弱)", 0.01, 0.04, 0.01)
        assert offset == -10

    def test_bearish_neutral(self):
        offset = compute_skew_offset("賣出 (動能轉弱)", 0.0, 0.0, 0.0)
        assert offset == 0

    def test_missing_iv_data_returns_zero(self):
        offset = compute_skew_offset("強烈買入 (爆發)", None, 0.03, -0.02)
        assert offset == 0

    def test_watch_converge_bullish(self):
        """WATCH_CONVERGE treated as bullish."""
        offset = compute_skew_offset("觀察 (跌勢收斂)", 0.03, 0.02, -0.01)
        assert offset == 10


class TestComputeFinalScoreV2:
    def test_base_plus_boost(self):
        assert compute_final_score_v2(70, 10) == 80.0

    def test_base_plus_penalty(self):
        assert compute_final_score_v2(85, -10) == 75.0

    def test_no_negative_floor(self):
        assert compute_final_score_v2(5, -10) == 0.0


class TestDetermineFinalAction:
    def test_downgraded(self):
        """score_delta < 0 takes top priority."""
        assert determine_final_action(90, -1) == "DOWNGRADED"

    def test_high_conviction(self):
        assert determine_final_action(90, 10) == "HIGH_CONVICTION"

    def test_buy_candidate(self):
        assert determine_final_action(78, 0) == "BUY_CANDIDATE"

    def test_watchlist(self):
        assert determine_final_action(68, 0) == "WATCHLIST"

    def test_no_trade_low_score(self):
        assert determine_final_action(50, 0) == "NO_TRADE"

    def test_no_trade_with_delta(self):
        """delta >=0 but score low → still NO_TRADE."""
        assert determine_final_action(60, 10) == "NO_TRADE"


class TestDetermineReason:
    def test_bullish_confirmed(self):
        r = determine_reason("強烈買入 (爆發)", 10, "bullish")
        assert "call skew confirmation" in r

    def test_bullish_contradicted(self):
        r = determine_reason("買入 (動能增強)", -10, "bearish")
        assert "Put skew contradicts" in r

    def test_bearish_confirmed(self):
        r = determine_reason("強烈賣出 (跌破)", 10, "bearish")
        assert "put skew confirmation" in r

    def test_bearish_contradicted(self):
        r = determine_reason("賣出 (動能轉弱)", -10, "bullish")
        assert "Call skew contradicts" in r

    def test_zero_offset(self):
        r = determine_reason("買入 (動能增強)", 0, "neutral")
        assert "No clear skew signal" in r


class TestAttachSkewToResult:
    def test_full_enrichment(self):
        result = {
            "ticker": "AAPL",
            "Signal": "強烈買入 (爆發)",
            "composite_score": 78,
            "is_squeezed": False,
            "fired": True,
            "momentum": 0.45,
        }
        skew_data = {
            "atm_iv": 0.25,
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
            "total_volume": 500,
            "avg_spread_pct": 0.05,
            "otm_call_distance": 0.05,
            "otm_put_distance": 0.05,
        }
        enriched = attach_skew_to_result(result, skew_data)

        # Layer 1 preserved
        assert enriched["ticker"] == "AAPL"
        assert enriched["Signal"] == "強烈買入 (爆發)"  # unchanged
        assert enriched["base_signal"] == "STRONG_BUY"
        assert enriched["base_score"] == 78
        assert enriched["squeeze_state"] == "Fired"

        # Layer 2 skew fields
        assert enriched["atm_iv"] == 0.25
        assert enriched["call_skew"] == 0.03
        assert enriched["skew_bias"] == "bullish"
        assert enriched["total_volume"] == 500
        assert enriched["avg_spread_pct"] == 0.05

        # Liquidity gate passes
        assert enriched["liquidity_ok"] is True
        assert "liquidity" not in enriched["reason"]

        # Computed — score_delta = skew_score_v2 directly
        # STRONG_BUY + risk_reversal>0 + call_skew>0 → +10 → delta=10
        assert enriched["skew_score_v2"] == 10
        assert enriched["score_delta"] == 10
        assert enriched["final_score_v2"] == 88
        assert enriched["final_action"] == "HIGH_CONVICTION"
        assert "call skew confirmation" in enriched["reason"]

    def test_bearish_downgrade(self):
        result = {
            "ticker": "TSLA",
            "Signal": "買入 (動能增強)",
            "composite_score": 82,
            "squeeze_on": True,
            "fired": False,
            "momentum": 0.12,
        }
        skew_data = {
            "atm_iv": 0.30,
            "call_skew": 0.01,
            "put_skew": 0.04,
            "risk_reversal": -0.03,
            "skew_bias": "bearish",
            "skew_score": -0.3,
            "total_volume": 300,
            "avg_spread_pct": 0.10,
            "otm_call_distance": 0.03,
            "otm_put_distance": 0.03,
        }
        enriched = attach_skew_to_result(result, skew_data)

        # BUY + put_skew(0.04) > call_skew(0.01) → -10
        assert enriched["base_signal"] == "BUY"
        assert enriched["skew_score_v2"] == -10
        assert enriched["score_delta"] == -10  # = skew_score_v2 directly
        # score_delta < 0 → DOWNGRADED (even though final_score=72)
        assert enriched["final_score_v2"] == 72
        assert enriched["final_action"] == "DOWNGRADED"
        assert "Put skew contradicts" in enriched["reason"]

    def test_signal_unchanged(self):
        result = {"ticker": "MSFT", "Signal": "觀望 (動能減弱)", "composite_score": 1}
        skew_data = {"skew_score": 0.8, "skew_bias": "bullish", "atm_iv": 0.25}
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["Signal"] == "觀望 (動能減弱)"

    # ── Protection 2: liquidity gate ──────────────────────────────────

    def test_liquidity_low_volume_gates_skew(self):
        result = {"ticker": "OBSCURE", "Signal": "強烈買入 (爆發)", "composite_score": 70}
        skew_data = {
            "atm_iv": 0.30,
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
            "total_volume": 10,     # < 50
            "avg_spread_pct": 0.10,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["liquidity_ok"] is False
        assert enriched["skew_score_v2"] == 0
        assert enriched["score_delta"] == 0
        assert enriched["final_score_v2"] == 70  # base score unchanged
        assert enriched["final_action"] == "NO_SKEW_DATA"
        assert "volume" in enriched["reason"]

    def test_liquidity_high_spread_gates_skew(self):
        result = {"ticker": "WIDE", "Signal": "強烈買入 (爆發)", "composite_score": 80}
        skew_data = {
            "atm_iv": 0.25,
            "call_skew": 0.03,
            "put_skew": -0.01,
            "risk_reversal": 0.04,
            "skew_bias": "bullish",
            "skew_score": 0.4,
            "total_volume": 500,
            "avg_spread_pct": 0.50,  # > 0.25
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["liquidity_ok"] is False
        assert enriched["skew_score_v2"] == 0
        assert enriched["score_delta"] == 0
        assert enriched["final_action"] == "NO_SKEW_DATA"
        assert "spread" in enriched["reason"]

    # ── Protection 3: IV overheated penalty ───────────────────────────

    def test_iv_overheated_applies_penalty(self):
        result = {"ticker": "HOT", "Signal": "強烈買入 (爆發)", "composite_score": 85}
        skew_data = {
            "atm_iv": 0.85,          # > 0.80 → overheated
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
            "total_volume": 500,
            "avg_spread_pct": 0.05,
            "otm_call_distance": 0.03,
            "otm_put_distance": 0.03,
        }
        enriched = attach_skew_to_result(result, skew_data)
        # base=85, IV overheated → bypass skew: base - 10 = 75, delta = -10
        assert enriched["skew_score_v2"] == 0  # skew not computed
        assert enriched["score_delta"] == -10
        assert enriched["final_score_v2"] == 75
        assert enriched["final_action"] == "AVOID_OVERHEATED_IV"
        assert "overheated" in enriched["reason"]
        assert "avoid chasing" in enriched["reason"]

    def test_iv_overheated_not_no_skew_data(self):
        """Regression: IV overheated must NOT return NO_SKEW_DATA
        even when liquidity and OTM distance both pass."""
        result = {"ticker": "HOT2", "Signal": "強烈買入 (爆發)", "composite_score": 78}
        skew_data = {
            "atm_iv": 0.82,          # > 0.80
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
            "total_volume": 999,     # liquid
            "avg_spread_pct": 0.05,  # tight spread
            "otm_call_distance": 0.02,  # close strikes
            "otm_put_distance": 0.02,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["final_action"] == "AVOID_OVERHEATED_IV", (
            f"Expected AVOID_OVERHEATED_IV but got {enriched['final_action']}"
        )
        assert enriched["score_delta"] == -10
        assert enriched["final_score_v2"] == 68  # 78 - 10
        assert enriched["skew_score_v2"] == 0  # skew bypassed
        assert enriched["liquidity_ok"] is True
        assert "NO_SKEW_DATA" not in enriched["final_action"]

    def test_iv_below_threshold_no_penalty(self):
        result = {"ticker": "COOL", "Signal": "強烈買入 (爆發)", "composite_score": 85}
        skew_data = {
            "atm_iv": 0.40,          # < 0.80 → fine
            "call_skew": 0.03,
            "put_skew": -0.02,
            "risk_reversal": 0.05,
            "skew_bias": "bullish",
            "skew_score": 0.5,
            "total_volume": 500,
            "avg_spread_pct": 0.05,
            "otm_call_distance": 0.05,
            "otm_put_distance": 0.05,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["final_score_v2"] == 95  # 85+10, no penalty
        assert enriched["final_action"] == "HIGH_CONVICTION"
        assert "IV" not in enriched["reason"]

    # ── Protection 4: OTM strike distance guard ───────────────────────

    def test_otm_call_distance_too_large(self):
        result = {"ticker": "WIDE", "Signal": "強烈買入 (爆發)", "composite_score": 75}
        skew_data = {
            "atm_iv": 0.30,
            "call_skew": 0.03,
            "put_skew": -0.01,
            "risk_reversal": 0.04,
            "skew_bias": "bullish",
            "skew_score": 0.4,
            "total_volume": 500,
            "avg_spread_pct": 0.05,
            "otm_call_distance": 0.15,  # > 0.10
            "otm_put_distance": 0.05,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["skew_score_v2"] == 0
        assert enriched["score_delta"] == 0
        assert enriched["final_score_v2"] == 75  # base unchanged
        assert enriched["final_action"] == "NO_SKEW_DATA"
        assert "otm_call_dist" in enriched["reason"]

    def test_otm_put_distance_too_large(self):
        result = {"ticker": "DEEP", "Signal": "買入 (動能增強)", "composite_score": 80}
        skew_data = {
            "atm_iv": 0.25,
            "call_skew": 0.02,
            "put_skew": -0.01,
            "risk_reversal": 0.03,
            "skew_bias": "bullish",
            "skew_score": 0.3,
            "total_volume": 300,
            "avg_spread_pct": 0.08,
            "otm_call_distance": 0.02,
            "otm_put_distance": 0.12,  # > 0.10
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["skew_score_v2"] == 0
        assert enriched["score_delta"] == 0
        assert enriched["final_action"] == "NO_SKEW_DATA"
        assert "otm_put_dist" in enriched["reason"]

    def test_otm_distance_both_ok_passes(self):
        result = {"ticker": "NORMAL", "Signal": "強烈買入 (爆發)", "composite_score": 80}
        skew_data = {
            "atm_iv": 0.30,
            "call_skew": 0.03,
            "put_skew": -0.01,
            "risk_reversal": 0.04,
            "skew_bias": "bullish",
            "skew_score": 0.4,
            "total_volume": 500,
            "avg_spread_pct": 0.05,
            "otm_call_distance": 0.03,
            "otm_put_distance": 0.03,
        }
        enriched = attach_skew_to_result(result, skew_data)
        assert enriched["skew_score_v2"] == 10  # skew applied normally
        assert enriched["score_delta"] == 10
        assert enriched["final_action"] == "HIGH_CONVICTION"


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
