import pandas as pd
import numpy as np
import pytest
from src.squeeze.engine.patterns import detect_houyi_shooting_sun, detect_whale_trading

def create_base_df(days=60):
    dates = pd.date_range(start='2020-01-01', periods=days)
    df = pd.DataFrame({
        'Open': np.linspace(100, 100, days),
        'High': np.linspace(100.1, 100.1, days),
        'Low': np.linspace(99.9, 99.9, days),
        'Close': np.linspace(100, 100, days),
        'Volume': 1000
    }, index=dates)
    return df

def test_houyi_perfect_setup():
    """Test Case 1: Perfect Houyi setup (Rally -> Fib Retrace -> Squeeze -> Shooting Star) -> Match."""
    days = 80
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # 1. Rally: 100 to 140 (40% gain) in first 30 days
    prices = np.linspace(100, 140, 31)
    
    # 2. Retrace: to 120 (0.5 Fib of 100-140) over next 20 days
    retrace = np.linspace(140, 120, 20)
    
    # 3. Consolidation: 120 for 29 days (to allow Squeeze to form)
    consolidation = np.full(29, 120.0)
    
    all_prices = np.concatenate([prices, retrace, consolidation])
    
    df = pd.DataFrame({
        'Open': all_prices,
        'High': all_prices + 0.01,
        'Low': all_prices - 0.01,
        'Close': all_prices,
        'Volume': 1000
    }, index=dates)
    
    # 4. Shooting Star at the last bar
    # Open=120, High=123, Low=119.9, Close=120.1
    # Real body = 0.1. Upper wick = 123 - 120.1 = 2.9. 2.9 >= 2 * 0.1 (True)
    last_idx = dates[-1]
    df.loc[last_idx, 'Open'] = 120.0
    df.loc[last_idx, 'High'] = 123.0
    df.loc[last_idx, 'Low'] = 119.9
    df.loc[last_idx, 'Close'] = 120.1
    
    result = detect_houyi_shooting_sun(df)
    assert result['is_houyi'] == True
    assert result['rally_pct'] >= 0.2
    assert 0.4 <= result['fib_level'] <= 0.75

def test_houyi_no_rally():
    """Test Case 2: No Rally -> No Match."""
    df = create_base_df(days=60)
    # Ensure it's squeezed and has a shooting star, but no preceding rally
    last_idx = df.index[-1]
    df.loc[last_idx, 'Open'] = 100.0
    df.loc[last_idx, 'High'] = 103.0
    df.loc[last_idx, 'Low'] = 99.9
    df.loc[last_idx, 'Close'] = 100.1
    
    result = detect_houyi_shooting_sun(df)
    assert result['is_houyi'] == False

def test_houyi_retrace_too_deep():
    """Test Case 3: Retrace too deep (> 0.75 Fib) -> No Match."""
    days = 60
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # Rally 100 -> 140
    prices = np.linspace(100, 140, 31)
    # Retrace to 105 (below 0.75 Fib which is 110)
    retrace = np.linspace(140, 105, 29)
    
    all_prices = np.concatenate([prices, retrace])
    df = pd.DataFrame({
        'Open': all_prices,
        'High': all_prices + 0.01,
        'Low': all_prices - 0.01,
        'Close': all_prices,
        'Volume': 1000
    }, index=dates)
    
    # Add shooting star
    last_idx = dates[-1]
    df.loc[last_idx, 'Open'] = 105.0
    df.loc[last_idx, 'High'] = 108.0
    df.loc[last_idx, 'Low'] = 104.9
    df.loc[last_idx, 'Close'] = 105.1
    
    result = detect_houyi_shooting_sun(df)
    assert result['is_houyi'] == False

def test_houyi_no_squeeze():
    """Test Case 4: No Squeeze -> No Match."""
    days = 60
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # Rally 100 -> 140
    prices = np.linspace(100, 140, 31)
    # Retrace to 120 (0.5 Fib)
    retrace = np.linspace(140, 120, 29)
    
    all_prices = np.concatenate([prices, retrace])
    df = pd.DataFrame({
        'Open': all_prices,
        'High': all_prices + 0.01,
        'Low': all_prices - 0.01,
        'Close': all_prices,
        'Volume': 1000
    }, index=dates)
    
    # Massive price spike to break squeeze
    last_idx = dates[-1]
    df.loc[last_idx, 'Open'] = 120.0
    df.loc[last_idx, 'Close'] = 500.0
    df.loc[last_idx, 'High'] = 1000.0
    df.loc[last_idx, 'Low'] = 119.0
    
    result = detect_houyi_shooting_sun(df)
    assert result['is_houyi'] == False

def test_whale_perfect_setup():
    """Test Case 1: Squeeze ON (Daily) + Squeeze ON (Weekly) + Momentum Positive -> Match."""
    # Need enough days for weekly indicators (e.g. 300 days ~= 60 weeks)
    days = 300
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # Constant price to allow squeeze to form on both timeframes
    # Use a small constant range for tight squeeze
    prices = np.full(days, 100.0)
    
    df = pd.DataFrame({
        'Open': prices,
        'High': prices + 0.01,
        'Low': prices - 0.01,
        'Close': prices,
        'Volume': 1000
    }, index=dates)
    
    # Give it a slight upward trend for positive momentum (gradual increase)
    trend = np.linspace(0, 10, days)
    df['Close'] += trend
    df['High'] += trend
    df['Low'] += trend
    df['Open'] += trend
    
    # We expect this to match because price is very stable (squeeze on) and trend is up
    result = detect_whale_trading(df)
    
    assert result['is_whale'] == True
    assert result['daily_squeeze'] == True
    assert result['weekly_squeeze'] == True
    assert result['daily_momentum'] > 0
    assert result['weekly_momentum'] > 0

def test_whale_only_daily_squeeze():
    """Test Case 2: Only Daily Squeeze -> No Match."""
    # Stable daily prices for the last 30 days to ensure daily squeeze is on
    # But volatile before that to ensure weekly squeeze is off
    days = 300
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # Volatile for most of the time
    prices = 100 + np.sin(np.linspace(0, 10*np.pi, days)) * 20
    # Stable for the last 30 days
    prices[-30:] = 100.0
    
    df = pd.DataFrame({
        'Open': prices,
        'High': prices + 0.1,
        'Low': prices - 0.1,
        'Close': prices,
        'Volume': 1000
    }, index=dates)
    
    result = detect_whale_trading(df)
    assert result['is_whale'] == False
    assert result['daily_squeeze'] == True
    assert result['weekly_squeeze'] == False

def test_whale_both_squeezed_negative_momentum():
    """Test Case 3: Both Squeezed but Momentum Negative -> No Match."""
    days = 300
    dates = pd.date_range(start='2020-01-01', periods=days)
    
    # Stable price for squeeze
    prices = np.full(days, 100.0)
    
    df = pd.DataFrame({
        'Open': prices,
        'High': prices + 0.01,
        'Low': prices - 0.01,
        'Close': prices,
        'Volume': 1000
    }, index=dates)
    
    # Slight downward trend for negative momentum
    trend = np.linspace(0, -10, days)
    df['Close'] += trend
    df['High'] += trend
    df['Low'] += trend
    df['Open'] += trend
    
    result = detect_whale_trading(df)
    assert result['is_whale'] == False
    # At least one momentum should be negative (likely both)
    assert result['daily_momentum'] < 0 or result['weekly_momentum'] < 0
