"""
Skew ranking integration: attaches options-skew confirmation scores
to existing squeeze results without altering base signals.

Produces a two-layer view:
  Layer 1: raw squeeze signal / base_score
  Layer 2: skew-adjusted final_score_v2, score_delta, final_action, reason
"""

import logging

logger = logging.getLogger(__name__)

# ── scoring scale constants ─────────────────────────────────────────────
# The skew_score offset lives in [-10, +10] and is OR'd onto a
# base_score that already scales 0-85+ via _signal_score + pattern flags.

SKEW_BOOST = 10   # maximum delta added by skew confirmation
SKEW_PENALTY = 10 # maximum delta subtracted by skew contradiction


def translate_base_signal(signal: str) -> str:
    """Map Chinese signal to English for the CSV/report."""
    mapping = {
        "強烈買入 (爆發)": "STRONG_BUY",
        "買入 (動能增強)": "BUY",
        "觀察 (跌勢收斂)": "WATCH_CONVERGE",
        "觀望 (動能減弱)": "HOLD_WEAKEN",
        "賣出 (動能轉弱)": "SELL",
        "強烈賣出 (跌破)": "STRONG_SELL",
    }
    return mapping.get(signal, signal)


def is_bullish_signal(signal: str) -> bool:
    return signal in ("STRONG_BUY", "BUY", "WATCH_CONVERGE")


def is_bearish_signal(signal: str) -> bool:
    return signal in ("STRONG_SELL", "SELL")


# ── quantised skew score ------------------------------------------------

def compute_skew_offset(
    signal: str,
    risk_reversal: float | None,
    call_skew: float | None,
    put_skew: float | None,
) -> int:
    """
    Return an integer offset in [-10, +10] based on the direction of the
    underlying squeeze signal and the skew structure.

    Bullish setup (base signal wants a long):
      risk_reversal > 0 AND call_skew > 0   → +10  (skew confirms)
      put_skew > call_skew                   → -10  (skew contradicts)

    Bearish setup (base signal wants a short):
      risk_reversal < 0 AND put_skew > 0    → +10  (skew confirms)
      call_skew > put_skew                   → -10  (skew contradicts)

    Neutral / unknown signal → offset = 0
    Missing IV data         → offset = 0
    """
    if risk_reversal is None or call_skew is None or put_skew is None:
        return 0

    eng_signal = translate_base_signal(signal)

    if is_bullish_signal(eng_signal):
        # Contradiction check first (stronger signal)
        if put_skew > call_skew:
            return -SKEW_PENALTY   # -10: skew contradicts bullish
        elif risk_reversal > 0 and call_skew > 0:
            return SKEW_BOOST      # +10: skew confirms bullish
        else:
            return 0

    if is_bearish_signal(eng_signal):
        # Contradiction check first
        if call_skew > put_skew:
            return -SKEW_PENALTY   # -10: skew contradicts bearish
        elif risk_reversal < 0 and put_skew > 0:
            return SKEW_BOOST      # +10: skew confirms bearish
        else:
            return 0

    return 0


def compute_final_score_v2(base_score: float, skew_offset: int) -> float:
    """final_score_v2 = composite_score (1-85+) + skew_offset."""
    return max(0.0, round(base_score + skew_offset, 4))


# ── final action & reason ───────────────────────────────────────────────

def determine_final_action(
    final_score: float,
    score_delta: float,
) -> str:
    """
    Map a (final_score, score_delta) pair to a human-readable action.
    """
    if final_score >= 85:
        return "High Conviction"
    elif final_score >= 70:
        return "Watch / Small Position"
    elif score_delta <= -15:
        return "Downgraded by Options Skew"
    else:
        return "No Trade"


def determine_reason(signal: str, skew_offset: int, skew_bias: str) -> str:
    """Produce a one-liner explaining the skew effect."""
    eng = translate_base_signal(signal)

    if skew_offset == 0:
        return "No clear skew signal"

    if skew_offset > 0:
        if is_bullish_signal(eng):
            return "Squeeze + call skew confirmation"
        elif is_bearish_signal(eng):
            return "Bearish squeeze + put skew confirmation"
        return f"Skew supportive ({skew_offset:+d})"

    # skew_offset < 0
    if is_bullish_signal(eng):
        return "Put skew contradicts bullish setup"
    elif is_bearish_signal(eng):
        return "Call skew contradicts bearish setup"
    return f"Skew contradictory ({skew_offset:+d})"


# ── main enrichment function ────────────────────────────────────────────

def attach_skew_to_result(result: dict, skew_data: dict) -> dict:
    """
    Return a new dict that merges all *skew_data* fields into *result*
    and adds the enriched view columns:

      ticker, base_signal, base_score, squeeze_state, momentum, volume_score
      atm_iv, call_skew, put_skew, risk_reversal, skew_bias, skew_score
      final_score_v2, score_delta, final_action, reason

    The original ``Signal`` field is never modified.

    ``skew_data`` must contain at least:
      atm_iv, call_skew, put_skew, risk_reversal, skew_bias, skew_score
    """
    enriched = dict(result)

    # -- layer 1: raw squeeze fields ------------------------------------
    raw_signal = result.get("Signal", "觀望")
    enriched["base_signal"] = translate_base_signal(raw_signal)
    enriched["base_score"] = result.get("composite_score", 0) or 0

    squeeze_on = bool(result.get("is_squeezed") or result.get("squeeze_on"))
    fired = bool(result.get("fired"))
    if fired:
        enriched["squeeze_state"] = "Fired"
    elif squeeze_on:
        enriched["squeeze_state"] = "Squeezing"
    else:
        enriched["squeeze_state"] = "Expanded"
    enriched["momentum"] = result.get("momentum", 0.0)

    # -- layer 2: skew fields -------------------------------------------
    enriched["atm_iv"] = skew_data.get("atm_iv")
    enriched["call_skew"] = skew_data.get("call_skew")
    enriched["put_skew"] = skew_data.get("put_skew")
    enriched["risk_reversal"] = skew_data.get("risk_reversal")
    enriched["skew_bias"] = skew_data.get("skew_bias", "neutral")
    enriched["skew_score"] = skew_data.get("skew_score", 0.0)

    # -- computed fields ------------------------------------------------
    signal_str = result.get("Signal", "觀望")
    rr = skew_data.get("risk_reversal")
    cs = skew_data.get("call_skew")
    ps = skew_data.get("put_skew")

    skew_offset = compute_skew_offset(signal_str, rr, cs, ps)
    enriched["skew_score_v2"] = skew_offset  # the -10..+10 quantised offset

    base = enriched["base_score"]
    enriched["final_score_v2"] = compute_final_score_v2(base, skew_offset)
    enriched["score_delta"] = round(enriched["final_score_v2"] - base, 4)
    enriched["final_action"] = determine_final_action(
        enriched["final_score_v2"], enriched["score_delta"],
    )
    enriched["reason"] = determine_reason(
        signal_str, skew_offset, enriched["skew_bias"],
    )

    return enriched


def compute_skew_score_for_result(result: dict, skew_data: dict) -> float:
    """Backward-compatible helper: return just final_score_v2."""
    return attach_skew_to_result(result, skew_data)["final_score_v2"]
