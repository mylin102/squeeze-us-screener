import pandas as pd
import requests
import urllib3
import io
from typing import List, Dict

# Suppress InsecureRequestWarning for when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_tickers() -> List[str]:
    """
    Backward compatibility for existing code.
    """
    mapping = fetch_tickers_with_names()
    return sorted(list(mapping.keys()))

def fetch_tickers_with_names() -> Dict[str, str]:
    """
    Fetch US tickers and names for S&P 500 and NASDAQ 100 from Wikipedia.
    Returns a dictionary mapping ticker symbols to names.
    """
    ticker_map = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    # 1. Fetch S&P 500
    try:
        sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        response = requests.get(sp500_url, headers=headers)
        sp500_tables = pd.read_html(io.StringIO(response.text))
        sp500_df = sp500_tables[0]
        for _, row in sp500_df.iterrows():
            symbol = str(row['Symbol']).replace('.', '-') # yfinance uses - for .
            name = str(row['Security'])
            ticker_map[symbol] = name
    except Exception as e:
        print(f"Error fetching S&P 500: {e}")

    # 2. Fetch NASDAQ 100
    try:
        nasdaq100_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        response = requests.get(nasdaq100_url, headers=headers)
        nasdaq_tables = pd.read_html(io.StringIO(response.text))
        for table in nasdaq_tables:
            if 'Ticker' in table.columns and 'Company' in table.columns:
                for _, row in table.iterrows():
                    symbol = str(row['Ticker'])
                    name = str(row['Company'])
                    ticker_map[symbol] = name
                break
    except Exception as e:
        print(f"Error fetching NASDAQ 100: {e}")

    # 3. Fetch Dow Jones Industrial Average (DJI)
    try:
        dji_url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
        response = requests.get(dji_url, headers=headers)
        dji_tables = pd.read_html(io.StringIO(response.text))
        # Usually the first or second table with 'Symbol' column
        for table in dji_tables:
            if 'Symbol' in table.columns:
                for _, row in table.iterrows():
                    symbol = str(row['Symbol']).replace('.', '-')
                    name = str(row['Company']) if 'Company' in row else symbol
                    ticker_map[symbol] = name
                break
    except Exception as e:
        print(f"Error fetching DJI: {e}")

    # 4. Add PHLX Semiconductor Sector (SOX) components
    # As Wikipedia page doesn't have a clean table, we include the 30 major components.
    # Note: use exact NASDAQ/NYSE ticker symbols only — avoid company abbreviations.
    sox_constituents = {
        'AMD':  'Advanced Micro Devices',   'ADI':  'Analog Devices',
        'AMAT': 'Applied Materials',        'ASML': 'ASML Holding',
        'AVGO': 'Broadcom',                 'KLAC': 'KLA Corporation',
        'LRCX': 'Lam Research',             'MRVL': 'Marvell Technology',
        'MCHP': 'Microchip Technology',     'MU':   'Micron Technology',
        'NVDA': 'NVIDIA',                   'NXPI': 'NXP Semiconductors',   # NXP is not a valid ticker
        'ON':   'ON Semiconductor',         'QCOM': 'Qualcomm',
        'TER':  'Teradyne',                 'TXN':  'Texas Instruments',
        'TSM':  'Taiwan Semiconductor',     'INTC': 'Intel',                # TSMC is not a valid US ticker
        'WOLF': 'Wolfspeed',                'ARM':  'Arm Holdings',
        'ENTG': 'Entegris',                 'GFS':  'GlobalFoundries',      # LSTK is not a valid ticker
        'MPWR': 'Monolithic Power Systems', 'RMBS': 'Rambus',
        'SLAB': 'Silicon Laboratories',     'STM':  'STMicroelectronics',   # STMicro is not a valid ticker
        'VRTX': 'Vertex Pharmaceuticals',
    }
    for symbol, name in sox_constituents.items():
        ticker_map[symbol] = name
                    
    return ticker_map


# ---------------------------------------------------------------------------
# ETF Universe — dual-role architecture (NOT mixed into stock rankings)
#
# Role 1 – Market/Sector benchmark: regime detection and stock confirmation.
# Role 2 – Independent ETF scanner: same squeeze pattern scan, separate output.
# ---------------------------------------------------------------------------

# Broad market ETFs — used for overall regime (bull/neutral/bear) detection
MARKET_ETFS: Dict[str, str] = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    "DIA": "Dow Jones",
}

# SPDR Sector ETFs — used for sector-level regime and RS context
SECTOR_ETFS: Dict[str, str] = {
    "XLK":  "Technology",
    "SMH":  "Semiconductors",
    "XLF":  "Financials",
    "XLI":  "Industrials",
    "XLE":  "Energy",
    "XLV":  "Healthcare",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication Services",
}

# Stock → primary sector ETF mapping
# Used (Phase 2+) for relative strength and breakout confirmation context.
# Defined here so it's co-located with the ETF lists for easy maintenance.
STOCK_SECTOR_MAP: Dict[str, str] = {
    # Semiconductors → SMH
    **{t: "SMH" for t in ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "AMAT", "LRCX",
                           "KLAC", "MU", "NXPI", "ON", "TXN", "ADI", "MCHP", "MRVL",
                           "ENTG", "GFS", "MPWR", "RMBS", "SLAB", "STM", "TER",
                           "WOLF", "ARM", "ASML", "TSM"]},
    # Broad Technology → XLK
    **{t: "XLK" for t in ["AAPL", "MSFT", "ORCL", "CRM", "ACN", "IBM", "ADBE",
                           "NOW", "INTU", "CSCO"]},
    # Financials → XLF
    **{t: "XLF" for t in ["JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK",
                           "SCHW", "C", "USB"]},
    # Healthcare → XLV
    **{t: "XLV" for t in ["JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "ABT",
                           "LLY", "BMY", "AMGN"]},
    # Energy → XLE
    **{t: "XLE" for t in ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX",
                           "VLO", "OXY", "HAL"]},
    # Consumer Discretionary → XLY
    **{t: "XLY" for t in ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX",
                           "TJX", "BKNG", "GM"]},
    # Communication Services → XLC
    **{t: "XLC" for t in ["META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA",
                           "TMUS", "T", "VZ"]},
    # Industrials → XLI
    **{t: "XLI" for t in ["HON", "UPS", "RTX", "CAT", "DE", "LMT", "BA",
                           "GE", "MMM", "FDX"]},
}


def get_etf_universe() -> Dict[str, str]:
    """
    Return the combined ETF universe (market + sector ETFs).

    These ETFs are scanned independently and their results appear in a
    dedicated section of the report — NOT mixed with the stock rankings.
    """
    return {**MARKET_ETFS, **SECTOR_ETFS}

