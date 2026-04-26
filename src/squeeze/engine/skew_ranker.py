"""
Skew ranking integration: attaches options-skew confirmation scores
to existing squeeze results without altering base signals.

Produces a two-layer view:
  Layer 1: raw squeeze signal / base_score
  Layer 2: skew-adjusted final_score_v2, score_delta, final_action, reason

Three protections prevent false signals:
  - score_delta = skew_score_v2 directly (transparent, no blending)
  - Liquidity gate: low volume or wide spread → NO_SKEW_DATA
  - IV overheated penalty: atm_iv >= 80% threshold → penalty
"""

import logging

logger = logging.getLogger(__name__)

# ── scoring scale constants ─────────────────────────────────────────────

SKEW_BOOST = 10       # max delta from skew confirmation
SKEW_PENALTY = 10     # max delta from skew contradiction
IV_OVERHEAT_PENALTY = 10  # penalty when IV is overheated

# Liquidity thresholds
MIN_OPTION_VOLUME = 50          # sum of ATM+OTM call+put volume
MAX_BID_ASK_SPREAD_PCT = 0.25   # 25% spread max

# IV threshold (absolute ATM IV as proxy for "overheated")
# When ATM IV exceeds this level we apply the penalty
IV_OVERHEATED_THRESHOLD = 0.80  # 80% IV

# OTM strike distance guard — if the gap between ATM and OTM strikes
# exceeds this proportion of spot, the skew signal is unreliable.
MAX_OTM_DISTANCE_PCT = 0.10  # 10% of spot


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

    Contradiction checked FIRST (stronger weight than confirmation).

    Bullish setup (base signal wants a long):
      put_skew > call_skew             → -10  (skew contradicts)
      risk_reversal > 0 AND call_skew > 0  → +10  (skew confirms)

    Bearish setup (base signal wants a short):
      call_skew > put_skew             → -10  (skew contradicts)
      risk_reversal < 0 AND put_skew > 0  → +10  (skew confirms)

    Neutral / unknown signal → offset = 0
    Missing IV data         → offset = 0
    """
    if risk_reversal is None or call_skew is None or put_skew is None:
        return 0

    eng_signal = translate_base_signal(signal)

    if is_bullish_signal(eng_signal):
        if put_skew > call_skew:
            return -SKEW_PENALTY
        elif risk_reversal > 0 and call_skew > 0:
            return SKEW_BOOST
        return 0

    if is_bearish_signal(eng_signal):
        if call_skew > put_skew:
            return -SKEW_PENALTY
        elif risk_reversal < 0 and put_skew > 0:
            return SKEW_BOOST
        return 0

    return 0


# ── liquidity check ────────────────────────────────────────────────────

def compute_liquidity_flags(
    total_volume: float | None,
    avg_spread_pct: float | None,
) -> tuple[bool, str]:
    """
    Check whether the option chain has sufficient liquidity.

    Returns (is_ok, reason_string).
    """
    reasons = []
    if total_volume is not None and total_volume < MIN_OPTION_VOLUME:
        reasons.append(f"volume={total_volume:.0f}<{MIN_OPTION_VOLUME}")
    if avg_spread_pct is not None and avg_spread_pct > MAX_BID_ASK_SPREAD_PCT:
        reasons.append(f"spread={avg_spread_pct:.1%}>{MAX_BID_ASK_SPREAD_PCT:.0%}")
    if reasons:
        return False, "Option liquidity too low: " + "; ".join(reasons)
    return True, ""


# ── IV overheated check ────────────────────────────────────────────────

def is_iv_overheated(atm_iv: float | None) -> tuple[bool, str]:
    """
    Check whether ATM IV suggests the option market is overheated.

    Returns (is_overheated, reason_suffix).
    """
    if atm_iv is not None and atm_iv >= IV_OVERHEATED_THRESHOLD:
        return True, f"IV rank too high ({atm_iv:.1%})"
    return False, ""


# ── OTM strike distance guard ──────────────────────────────────────────

def check_otm_distance_ok(
    otm_call_distance: float | None,
    otm_put_distance: float | None,
) -> tuple[bool, str]:
    """
    Verify that the OTM strikes aren't too far from ATM.

    If the gap between ATM and the selected OTM strike exceeds
    MAX_OTM_DISTANCE_PCT of spot, the skew signal is unreliable.

    Returns (is_ok, reason_string).
    """
    reasons = []
    if otm_call_distance is not None and otm_call_distance > MAX_OTM_DISTANCE_PCT:
        reasons.append(f"otm_call_dist={otm_call_distance:.2%}>{MAX_OTM_DISTANCE_PCT:.0%}")
    if otm_put_distance is not None and otm_put_distance > MAX_OTM_DISTANCE_PCT:
        reasons.append(f"otm_put_dist={otm_put_distance:.2%}>{MAX_OTM_DISTANCE_PCT:.0%}")
    if reasons:
        return False, "OTM strike distance too large: " + "; ".join(reasons)
    return True, ""


# ── final score & action ───────────────────────────────────────────────

def compute_final_score_v2(base_score: float, skew_offset: int) -> float:
    """final_score_v2 = base_score + skew_offset (floor 0)."""
    return max(0.0, round(base_score + skew_offset, 4))


def determine_final_action(
    final_score: float,
    score_delta: float,
) -> str:
    """
    Map (final_score, score_delta) to a human-readable action.

    Tier priority:
      1. score_delta < 0       → DOWNGRADED
      2. final_score >= 85 AND score_delta > 0  → HIGH_CONVICTION
      3. final_score >= 75 AND score_delta >= 0 → BUY_CANDIDATE
      4. final_score >= 65     → WATCHLIST
      5. Otherwise             → NO_TRADE
    """
    if score_delta < 0:
        return "DOWNGRADED"
    if final_score >= 85 and score_delta > 0:
        return "HIGH_CONVICTION"
    if final_score >= 75 and score_delta >= 0:
        return "BUY_CANDIDATE"
    if final_score >= 65:
        return "WATCHLIST"
    return "NO_TRADE"


def determine_reason(base_signal: str, skew_offset: int, skew_bias: str) -> str:
    """Produce a one-liner explaining the skew effect."""
    eng = translate_base_signal(base_signal)

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

      ticker, base_signal, base_score, squeeze_state, momentum,
      atm_iv, call_skew, put_skew, risk_reversal, skew_bias,
      skew_score_v2, total_volume, avg_spread_pct,
      liquidity_ok, iv_overheated,
      final_score_v2, score_delta, final_action, reason

    The original ``Signal`` field is never modified.

    ``skew_data`` should contain (at minimum):
      atm_iv, call_skew, put_skew, risk_reversal, skew_bias, skew_score,
      total_volume, avg_spread_pct
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
    atm_iv = skew_data.get("atm_iv")
    call_skew_val = skew_data.get("call_skew")
    put_skew_val = skew_data.get("put_skew")
    rr = skew_data.get("risk_reversal")
    skew_bias = skew_data.get("skew_bias", "neutral")
    total_volume = skew_data.get("total_volume")
    avg_spread_pct = skew_data.get("avg_spread_pct")
    otm_call_distance = skew_data.get("otm_call_distance")
    otm_put_distance = skew_data.get("otm_put_distance")

    enriched["atm_iv"] = atm_iv
    enriched["call_skew"] = call_skew_val
    enriched["put_skew"] = put_skew_val
    enriched["risk_reversal"] = rr
    enriched["skew_bias"] = skew_bias
    enriched["total_volume"] = total_volume
    enriched["avg_spread_pct"] = avg_spread_pct
    enriched["otm_call_distance"] = otm_call_distance
    enriched["otm_put_distance"] = otm_put_distance

    # -- Protection 2: liquidity gate -----------------------------------
    liquidity_ok, liquidity_reason = compute_liquidity_flags(total_volume, avg_spread_pct)
    enriched["liquidity_ok"] = liquidity_ok

    if not liquidity_ok:
        enriched["skew_score_v2"] = 0
        enriched["final_score_v2"] = enriched["base_score"]
        enriched["score_delta"] = 0
        enriched["final_action"] = "NO_SKEW_DATA"
        enriched["reason"] = liquidity_reason
        return enriched

    # -- Protection 4: OTM strike distance guard ------------------------
    otm_distance_ok, otm_distance_reason = check_otm_distance_ok(otm_call_distance, otm_put_distance)

    if not otm_distance_ok:
        enriched["skew_score_v2"] = 0
        enriched["final_score_v2"] = enriched["base_score"]
        enriched["score_delta"] = 0
        enriched["final_action"] = "NO_SKEW_DATA"
        enriched["reason"] = otm_distance_reason
        return enriched

    # -- Protection 3: IV overheated penalty ----------------------------
    iv_overheated, iv_reason = is_iv_overheated(atm_iv)
    enriched["iv_overheated"] = iv_overheated

    # -- compute skew offset --------------------------------------------
    skew_offset = compute_skew_offset(raw_signal, rr, call_skew_val, put_skew_val)
    enriched["skew_score_v2"] = skew_offset

    # Protection 1: score_delta = skew_score_v2 directly (the -10..+10)
    enriched["score_delta"] = float(skew_offset)

    base = enriched["base_score"]
    final = compute_final_score_v2(base, skew_offset)

    if iv_overheated:
        final = max(0.0, final - IV_OVERHEAT_PENALTY)

    enriched["final_score_v2"] = final
    enriched["final_action"] = determine_final_action(final, float(skew_offset))
    enriched["reason"] = determine_reason(raw_signal, skew_offset, skew_bias)

    if iv_overheated:
        enriched["final_action"] = "AVOID_OVERHEATED_IV"
        enriched["reason"] += "; " + iv_reason

    return enriched


def compute_skew_score_for_result(result: dict, skew_data: dict) -> float:
    """Backward-compatible helper: return just final_score_v2."""
    return attach_skew_to_result(result, skew_data)["final_score_v2"]
