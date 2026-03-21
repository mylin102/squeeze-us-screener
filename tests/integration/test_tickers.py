import pytest
from squeeze.data.tickers import fetch_tickers

def test_fetch_tickers_integration():
    """
    Integration test for fetching tickers from official sources.
    Ensures that we get a list of common stocks including some well-known ones.
    """
    tickers = fetch_tickers()
    
    # Should be a list
    assert isinstance(tickers, list)
    
    # Should have more than 500 items (S&P 500 + NASDAQ 100)
    assert len(tickers) >= 500
    
    # Should contain some known tickers
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "GOOGL" in tickers or "GOOG" in tickers
    
    # Tickers should be alphabetic symbols (mostly)
    for t in tickers:
        assert t.isalnum() or '-' in t
