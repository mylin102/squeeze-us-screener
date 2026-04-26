# 基於追蹤報告的 Squeeze 策略回測框架 (US Market)

## 概述

本文件定義如何根據 `recommendations.csv` 追蹤報告進行系統性回測，專為**美國股市**設計。利用歷史推薦記錄驗證不同策略配置的實際表現。

---

## 一、美股市場特性

### 1.1 與 CN/TW 市場差異

| 特性 | 美股 (US) | 中國 A 股 (CN) | 台灣股市 (TW) |
|------|----------|--------------|--------------|
| 交易時間 | 9:30-16:00 ET | 9:30-15:00 CST | 9:00-13:30 TWT |
| 漲跌幅限制 | 無 (有熔斷) | ±10% (科創/創業±20%) | ±10% |
| 交易單位 | 1 股 | 100 股 (1 張) | 1000 股 (1 張) |
| 放空規則 | T+0, 較寬鬆 | 限制較多 | 限制較多 |
| 基準指數 | SPY/QQQ/IWM | 000300.SS | 0050.TW |

### 1.2 美股 Universe

預設掃描範圍：
- **S&P 500** (~500 檔)
- **NASDAQ 100** (~100 檔)
- **Dow Jones** (~30 檔)
- **Russell 2000** (~2000 檔，可選)
- **SOX 費城半導體** (~30 檔)

---

## 二、美股專用策略配置

### 2.1 預設策略表

| 策略名稱 | 描述 | 關鍵參數 | 適用情境 |
|---------|------|---------|---------|
| `baseline` | 基準策略 | 無過濾器 | 所有市場 |
| `momentum_focus` | 動能突破 | `min_momentum=0.05`, `require_fired=True` | 多頭市場 |
| `whale_alignment` | 日週線共振 | `patterns=["whale"]`, `holding_days=10` | 趨勢明確 |
| `bull_market` | 多頭專用 | `allowed_regimes=["bull_trend"]` | 多頭 |
| `bear_defense` | 空頭放空 | `signal_types=["sell"]`, `allowed_regimes=["bear_trend"]` | 空頭 |
| `high_conviction` | 高信心 | `min_energy_level=3`, `min_value_score=0.7` | 精選標的 |
| `magnificent_7` | 科技巨頭 | `tickers=["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA"]` | 大型股 |
| `semiconductor` | 半導體專用 | `sector="SOX"`, `holding_days=7` | 半導體 |

### 2.2 美股專用參數

```python
US_SPECIFIC_PARAMS = {
    # 進場過濾器
    "min_price": 5.0,            # 最小股價 (USD)
    "max_price": None,           # 最大股價
    "min_volume": 500000,        # 最小日均成交量
    "min_market_cap": 2e9,       # 最小市值 (2B USD)
    
    # 財報回避
    "avoid_earnings": True,      # 避免財報週期
    "earnings_window": 5,        # 財報前後 N 天
    
    # 行業偏好
    "sectors": None,             # None=全部，或 ["Technology", "Healthcare"]
    "exclude_sectors": ["Utilities", "Real Estate"],  # 排除行業
    
    # 指數成份股偏好
    "sp500_only": False,         # 僅 S&P 500
    "nasdaq100_only": False,     # 僅 NASDAQ 100
}
```

---

## 三、回測執行流程

### 3.1 數據準備

```python
import pandas as pd
from pathlib import Path

def load_us_tracking_data(csv_path: str) -> pd.DataFrame:
    """載入美股追蹤數據"""
    df = pd.read_csv(csv_path)
    
    # 標準化欄位
    required_columns = [
        'date', 'ticker', 'name', 'entry_price', 'signal',
        'strategy_return_pct', 'days_tracked', 'status',
        'type', 'pattern', 'momentum', 'energy_level',
        'squeeze_on', 'fired', 'market_regime'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            if col == 'strategy_return_pct':
                df[col] = df['return_pct'] if df['type'].iloc[0] == 'buy' else -df['return_pct']
            else:
                df[col] = None
    
    return df

def filter_completed(df: pd.DataFrame) -> pd.DataFrame:
    """只保留已完成追蹤的記錄"""
    return df[df["status"] == "completed"].copy()
```

### 3.2 美股專用回測引擎

```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class USBacktestResult:
    strategy_name: str
    params: Dict
    total_trades: int
    win_rate: float
    avg_return: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    sector_breakdown: Dict[str, float]  # 行業分佈
    index_comparison: Dict[str, float]  # 指數比較

def run_us_backtest(
    df: pd.DataFrame,
    params: Dict,
    strategy_name: str = "custom",
    benchmark: str = "SPY"
) -> USBacktestResult:
    """
    美股專用回測，包含行業和指數比較
    """
    filtered = df.copy()
    
    # 1. 形態過濾
    if params.get("patterns"):
        filtered = filtered[filtered["pattern"].isin(params["patterns"])]
    
    # 2. 方向過濾
    if params.get("signal_types"):
        filtered = filtered[filtered["type"].isin(params["signal_types"])]
    
    # 3. 動能過濾
    if params.get("min_momentum") is not None:
        filtered = filtered[filtered["momentum"] >= params["min_momentum"]]
    if params.get("require_fired"):
        filtered = filtered[filtered["fired"] == True]
    
    # 4. 擠壓狀態過濾
    if params.get("require_squeeze_on"):
        filtered = filtered[filtered["squeeze_on"] == True]
    if params.get("min_energy_level") is not None:
        filtered = filtered[filtered["energy_level"] >= params["min_energy_level"]]
    
    # 5. 市場狀態過濾
    if params.get("allowed_regimes"):
        filtered = filtered[filtered["market_regime"].isin(params["allowed_regimes"])]
    
    # 6. 持有天數過濾
    holding_days = params.get("holding_days", 14)
    filtered = filtered[filtered["days_tracked"] <= holding_days]
    
    # 7. 價格過濾 (美股特色)
    if params.get("min_price") is not None:
        filtered = filtered[filtered["entry_price"] >= params["min_price"]]
    
    # 8. 成交量過濾
    if params.get("min_volume") is not None:
        # 假設有 volume 欄位
        if "volume" in filtered.columns:
            filtered = filtered[filtered["volume"] >= params["min_volume"]]
    
    # 計算績效
    if filtered.empty:
        return USBacktestResult(
            strategy_name=strategy_name,
            params=params,
            total_trades=0,
            win_rate=0.0,
            avg_return=0.0,
            total_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            profit_factor=0.0,
            sector_breakdown={},
            index_comparison={}
        )
    
    returns = filtered["strategy_return_pct"]
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    
    total_trades = len(filtered)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    avg_return = returns.mean()
    total_return = returns.sum()
    
    # Sharpe Ratio
    daily_returns = filtered.groupby("date")["strategy_return_pct"].sum()
    sharpe_ratio = (daily_returns.mean() / daily_returns.std() * (252 ** 0.5)) if len(daily_returns) > 1 else 0
    
    # 最大回撤
    cumulative = (1 + daily_returns / 100).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdowns = (cumulative / rolling_max) - 1
    max_drawdown = drawdowns.min() * 100
    
    # 盈虧比
    profit_factor = wins.sum() / abs(losses.sum()) if len(losses) > 0 else float('inf')
    
    # 行業分析 (如果有 sector 資料)
    sector_breakdown = {}
    if "sector" in filtered.columns:
        sector_breakdown = filtered.groupby("sector")["strategy_return_pct"].sum().to_dict()
    
    # 指數比較 (簡化版)
    index_comparison = {
        "strategy": total_return,
        "benchmark": 0.0,  # 需要額外下載基準數據
        "excess": total_return
    }
    
    return USBacktestResult(
        strategy_name=strategy_name,
        params=params,
        total_trades=total_trades,
        win_rate=win_rate,
        avg_return=round(avg_return, 2),
        total_return=round(total_return, 2),
        sharpe_ratio=round(sharpe_ratio, 2),
        max_drawdown=round(max_drawdown, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else 99.99,
        sector_breakdown=sector_breakdown,
        index_comparison=index_comparison
    )
```

### 3.3 批量回測

```python
def get_us_strategies() -> Dict[str, Dict]:
    """返回美股專用策略配置"""
    return {
        "baseline": {
            "min_momentum": None,
            "require_squeeze_on": False,
            "require_fired": False,
            "patterns": ["squeeze", "houyi", "whale"],
            "signal_types": ["buy"],
            "holding_days": 14,
            "allowed_regimes": None,
        },
        "momentum_focus": {
            "min_momentum": 0.05,
            "require_fired": True,
            "patterns": ["squeeze"],
            "signal_types": ["buy"],
            "holding_days": 14,
        },
        "whale_alignment": {
            "patterns": ["whale"],
            "signal_types": ["buy"],
            "holding_days": 10,
        },
        "bull_market": {
            "allowed_regimes": ["bull_trend"],
            "patterns": ["squeeze", "houyi", "whale"],
            "signal_types": ["buy"],
            "holding_days": 14,
        },
        "bear_defense": {
            "signal_types": ["sell"],
            "allowed_regimes": ["bear_trend"],
            "holding_days": 14,
        },
        "high_conviction": {
            "min_energy_level": 3,
            "min_value_score": 0.7,
            "patterns": ["squeeze", "houyi"],
            "signal_types": ["buy"],
            "holding_days": 7,
        },
    }

def compare_us_strategies(df: pd.DataFrame) -> pd.DataFrame:
    """比較所有美股策略的表現"""
    strategies = get_us_strategies()
    
    results = []
    for name, params in strategies.items():
        result = run_us_backtest(df, params, name)
        results.append(result)
    
    records = [
        {
            "Strategy": r.strategy_name,
            "Trades": r.total_trades,
            "Win Rate %": r.win_rate,
            "Avg Return %": r.avg_return,
            "Total Return %": r.total_return,
            "Sharpe": r.sharpe_ratio,
            "Max DD %": r.max_drawdown,
            "Profit Factor": r.profit_factor,
        }
        for r in results
    ]
    
    return pd.DataFrame(records).sort_values("Total Return %", ascending=False)
```

---

## 四、美股專用分析維度

### 4.1 行業分析

```python
def analyze_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """分析各行業表現"""
    if "sector" not in df.columns:
        return pd.DataFrame()
    
    completed = df[df["status"] == "completed"]
    
    stats = completed.groupby("sector").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean"),
        total_return=("strategy_return_pct", "sum")
    ).reset_index().sort_values("total_return", ascending=False)
    
    return stats
```

### 4.2 市值分析

```python
def analyze_by_market_cap(df: pd.DataFrame) -> pd.DataFrame:
    """分析不同市值區間表現"""
    if "market_cap" not in df.columns:
        return pd.DataFrame()
    
    completed = df[df["status"] == "completed"]
    
    def cap_bucket(cap: float) -> str:
        if cap < 2e9:
            return "Micro (<2B)"
        elif cap < 10e9:
            return "Small (2-10B)"
        elif cap < 200e9:
            return "Mid (10-200B)"
        else:
            return "Large (>200B)"
    
    completed = completed.copy()
    completed["cap_bucket"] = completed["market_cap"].apply(cap_bucket)
    
    stats = completed.groupby("cap_bucket").agg(
        trades=("ticker", "count"),
        win_rate=("strategy_return_pct", lambda x: (x > 0).mean() * 100),
        avg_return=("strategy_return_pct", "mean")
    ).reset_index()
    
    return stats
```

### 4.3 指數成份股分析

```python
def analyze_by_index_membership(df: pd.DataFrame) -> Dict[str, float]:
    """分析指數成份股表現"""
    completed = df[df["status"] == "completed"]
    
    # 定義指數成份股
    sp500_tickers = {...}  # 需要外部數據
    nasdaq100_tickers = {...}
    
    results = {}
    
    # S&P 500
    sp500 = completed[completed["ticker"].isin(sp500_tickers)]
    if len(sp500) > 0:
        results["SP500"] = sp500["strategy_return_pct"].mean()
    
    # NASDAQ 100
    nasdaq100 = completed[completed["ticker"].isin(nasdaq100_tickers)]
    if len(nasdaq100) > 0:
        results["NASDAQ100"] = nasdaq100["strategy_return_pct"].mean()
    
    # Others
    others = completed[~completed["ticker"].isin(sp500_tickers + nasdaq100_tickers)]
    if len(others) > 0:
        results["Others"] = others["strategy_return_pct"].mean()
    
    return results
```

---

## 五、執行命令

### 5.1 基本回測

```bash
cd /Users/mylin/Documents/mylin102/squeeze-us-screener

# 使用通用回測框架
squeeze-backtest run -c recommendations.csv -m us

# 或使用快速腳本
PYTHONPATH=../squeeze-backtest/src python3 ../squeeze-backtest/scripts/quick_backtest.py \
    --csv recommendations.csv \
    --market us
```

### 5.2 指定策略

```bash
# 只執行特定策略
squeeze-backtest run -c recommendations.csv -m us \
    -s momentum_focus \
    -s whale_alignment \
    -s bear_defense

# 輸出 JSON
squeeze-backtest run -c recommendations.csv -m us --json
```

---

## 六、美股注意事項

### 6.1 財報季節

```python
def avoid_earnings_season(df: pd.DataFrame, earnings_dates: Dict[str, str]) -> pd.DataFrame:
    """避免財報期間的交易"""
    filtered = df.copy()
    
    for idx, row in filtered.iterrows():
        ticker = row["ticker"]
        trade_date = pd.to_datetime(row["date"])
        
        if ticker in earnings_dates:
            earnings_date = pd.to_datetime(earnings_dates[ticker])
            days_diff = abs((trade_date - earnings_date).days)
            
            if days_diff <= 5:  # 財報前後 5 天
                filtered = filtered.drop(idx)
    
    return filtered
```

### 6.2 熔斷機制

美股有三級熔斷：
- **Level 1**: -7% 暫停 15 分鐘
- **Level 2**: -13% 暫停 15 分鐘
- **Level 3**: -20% 停止交易

回測時需考慮熔斷對進出場的影響。

### 6.3 ADR 與港股

部分中概股以 ADR 形式在美股交易：
- BABA (阿里巴巴)
- JD (京東)
- PDD (拼多多)

這些標的可能受中國政策影響，需單獨分析。

---

## 七、策略調整建議生成

```python
def generate_us_recommendations(
    results_df: pd.DataFrame,
    completed: pd.DataFrame,
    sector_analysis: pd.DataFrame = None
) -> List[str]:
    """生成美股專用建議"""
    recs = []
    
    if len(results_df) == 0:
        return ["數據不足，無法生成建議"]
    
    best = results_df.iloc[0]
    
    # 檢查放空策略
    sell_strategies = results_df[results_df["Strategy"] == "bear_defense"]
    if len(sell_strategies) > 0 and sell_strategies.iloc[0]["Total Return %"] > 0:
        recs.append("放空策略獲利，建議在空頭市場增加放空操作")
    
    # 檢查行業集中度
    if sector_analysis is not None and len(sector_analysis) > 0:
        top_sector = sector_analysis.iloc[0]
        if top_sector["total_return"] > 20:
            recs.append(f"行業 '{top_sector['sector']}' 表現優異，可考慮增加配置")
    
    # 檢查最大回撤
    if best["Max DD %"] < -25:
        recs.append(f"最大回撤 {best['Max DD %']:.2f}% 過大，建議加入停損或減少倉位")
    
    # 檢查 Sharpe
    if best["Sharpe"] > 2.0:
        recs.append(f"Sharpe 比率 {best['Sharpe']:.2f} 優秀，策略風險調整後報酬佳")
    
    if not recs:
        recs.append("目前策略表現良好，持續追蹤並累積更多數據")
    
    return recs
```

---

## 八、範例報告結構

```markdown
# Squeeze 美股策略回測報告

**市場**: 美國股市 (US)
**基準指數**: SPY
**報告日期**: 2026-03-28
**數據範圍**: 2026-01-01 至 2026-03-28

## 策略比較
[策略比較表格]

## 最佳策略分析
[詳細分析]

## 行業分析
[各行業表現]

## 指數比較
- 策略報酬：XX%
- SPY 報酬：XX%
- 超額報酬：XX%

## 策略建議
[自動生成建議]
```

---

*文件版本：v1.0 (US Market)*
*建立日期：2026-03-28*
*適用專案：squeeze-us-screener v1.2.1+*
