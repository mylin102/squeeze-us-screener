Squeeze Tracking Analysis
- Total records: 26
- Completed records: 25
- Active records: 1
- Date range: 2026-04-24 to 2026-07-13

By Type
- bucket=buy | n=13 | win=69.2% | avg=3.18% | median=1.59%
- bucket=sell | n=12 | win=50.0% | avg=-7.15% | median=-3.40%

By Signal
- direction=buy | bucket=強烈買入 (爆發) | n=4 | win=75.0% | avg=7.40% | median=4.88%
- direction=buy | bucket=買入 (動能增強) | n=9 | win=66.7% | avg=1.31% | median=1.41%
- direction=sell | bucket=賣出 (動能轉弱) | n=5 | win=40.0% | avg=-3.58% | median=-7.35%
- direction=sell | bucket=強烈賣出 (跌破) | n=7 | win=57.1% | avg=-9.70% | median=0.55%

By Holding Day
- bucket=79 | n=20 | win=60.0% | avg=-1.09% | median=1.48%
- bucket=80 | n=5 | win=60.0% | avg=-4.54% | median=1.41%

By Regime
- bucket=bull_trend | direction=buy | n=13 | win=69.2% | avg=3.18% | median=1.59%
- bucket=bull_trend | direction=sell | n=12 | win=50.0% | avg=-7.15% | median=-3.40%

By Holding Bucket
- bucket=11-14d | direction=buy | n=13 | win=69.2% | avg=3.18% | median=1.59%
- bucket=11-14d | direction=sell | n=12 | win=50.0% | avg=-7.15% | median=-3.40%

Feature Comparison (True vs False)
  Feature              n_True n_False    Avg_T    Avg_F    Diff%  Win_T  Win_F
  Hit 5% 14d                8     17     5.4%    -7.1%   +12.5%  25.0%  76.5%

Pattern Combination Performance
  Combo                                  n  Avg 14D   Win%
  Squeeze+Houyi+Whale                   25    -1.8%  60.0%

Recommendations
- Sell signals are not benefiting from downside follow-through. Recheck bearish signal definitions and short-side ranking.
- Best holding window is 11-14d (3.18%). Worst window is 11-14d (-7.15%). Use this to revisit exit timing.
- Signals with repeat underperformance: sell:賣出 (動能轉弱), sell:強烈賣出 (跌破). Review the indicator thresholds behind these buckets.
- Best differentiating feature: Hit 5% 14d (True vs False: +12.5% return difference). Consider increasing its weight.