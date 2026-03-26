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
    # As Wikipedia page doesn't have a clean table, we include the 30 major components
    sox_constituents = {
        'AMD': 'Advanced Micro Devices', 'ADI': 'Analog Devices', 'AMAT': 'Applied Materials',
        'ASML': 'ASML Holding', 'AVGO': 'Broadcom', 'KLAC': 'KLA Corporation',
        'LRCX': 'Lam Research', 'MRVL': 'Marvell Technology', 'MCHP': 'Microchip Technology',
        'MU': 'Micron Technology', 'NVDA': 'NVIDIA', 'NXP': 'NXP Semiconductors',
        'ON': 'ON Semiconductor', 'QCOM': 'Qualcomm', 'TER': 'Teradyne',
        'TXN': 'Texas Instruments', 'TSM': 'Taiwan Semiconductor', 'INTC': 'Intel',
        'WOLF': 'Wolfspeed', 'ARM': 'Arm Holdings', 'ENTG': 'Entegris',
        'LSTK': 'GlobalFoundries', 'MPWR': 'Monolithic Power Systems', 'NXPI': 'NXP Semiconductors',
        'RMBS': 'Rambus', 'SLAB': 'Silicon Laboratories', 'STMicro': 'STMicroelectronics',
        'TSMC': 'Taiwan Semiconductor', 'VRTX': 'Vertex Pharmaceuticals', 'GFS': 'GlobalFoundries'
    }
    for symbol, name in sox_constituents.items():
        ticker_map[symbol] = name
                    
    return ticker_map
