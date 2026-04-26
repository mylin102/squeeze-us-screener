"""
Skew ranking integration: attaches options-skew confirmation scores
to existing squeeze results without altering base signals.
"""

import logging

logger = logging.getLogger(__name__)


def compute_skew_score_for_result(result: dict, skew_data: dict) -> float:
    """
    Combine the existing ``composite_score`` (from squeeze + patterns) with
    the options-skew confirmation.

    ``final_score_v2 = composite_score + skew_score``

    Where ``skew_score`` ranges [-1, 1] (positive = bullish skew confirms
    a buy signal; negative = bearish skew).

    The original result's ``Signal`` field is *not* changed.
    """
    base = result.get("composite_score", 0) or 0
    skew = skew_data.get("skew_score", 0.0) or 0.0
    return round(base + skew, 4)


def attach_skew_to_result(result: dict, skew_data: dict) -> dict:
    """
    Return a new dict that merges all *skew_data* fields into *result*
    and adds ``final_score_v2``.

    Original fields are preserved.
    """
    enriched = dict(result)
    enriched.update(skew_data)
    enriched["final_score_v2"] = compute_skew_score_for_result(result, skew_data)
    return enriched
