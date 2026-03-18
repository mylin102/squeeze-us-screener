import requests
import pandas as pd
import matplotlib.pyplot as plt
import time
import os

# API 配置
API_KEY = '4TIPK6NIMJ0SC8KZ'
SYMBOL = 'CCJ'
BASE_URL = 'https://www.alphavantage.co/query'

def fetch_alpha_vantage_data(function, symbol, extra_params=None):
    params = {
        'function': function,
        'symbol': symbol,
        'apikey': API_KEY
    }
    if extra_params:
        params.update(extra_params)
    
    response = requests.get(BASE_URL, params=params)
    data = response.json()
    
    # 檢查是否有頻率限制訊息
    if "Note" in data:
        print(f"⚠️ API 限制提示: {data['Note']}")
        time.sleep(15)  # 等待 15 秒後重試一次
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
    return data

def main():
    print(f"🚀 正在從 Alpha Vantage 抓取 {SYMBOL} 的數據...")
    
    # 1. 獲取每日股價 (TIME_SERIES_DAILY)
    price_data = fetch_alpha_vantage_data('TIME_SERIES_DAILY', SYMBOL)
    if "Time Series (Daily)" not in price_data:
        print("❌ 錯誤：無法獲取股價數據。")
        print(price_data)
        return

    df_price = pd.DataFrame.from_dict(price_data['Time Series (Daily)'], orient='index')
    df_price.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    df_price.index = pd.to_datetime(df_price.index)
    df_price = df_price.astype(float).sort_index()
    df_price = df_price.tail(30)

    # 為了避免頻率限制，每次請求間隔一下
    time.sleep(2)

    # 2. 獲取 RSI 指標
    rsi_data = fetch_alpha_vantage_data('RSI', SYMBOL, {'interval': 'daily', 'time_period': '14', 'series_type': 'close'})
    df_rsi = pd.DataFrame()
    if 'Technical Analysis: RSI' in rsi_data:
        df_rsi = pd.DataFrame.from_dict(rsi_data['Technical Analysis: RSI'], orient='index')
        df_rsi.index = pd.to_datetime(df_rsi.index)
        df_rsi = df_rsi.astype(float).sort_index()
    else:
        print("⚠️ 無法獲取 RSI 數據，將在圖表中跳過。")

    time.sleep(2)

    # 3. 獲取 MACD 指標
    macd_data = fetch_alpha_vantage_data('MACD', SYMBOL, {'interval': 'daily', 'series_type': 'close'})
    df_macd = pd.DataFrame()
    if 'Technical Analysis: MACD' in macd_data:
        df_macd = pd.DataFrame.from_dict(macd_data['Technical Analysis: MACD'], orient='index')
        df_macd.index = pd.to_datetime(df_macd.index)
        df_macd = df_macd.astype(float).sort_index()
    else:
        print("⚠️ 無法獲取 MACD 數據，將在圖表中跳過。")

    # 合併數據
    df_plot = df_price.copy()
    if not df_rsi.empty:
        df_plot = df_plot.join(df_rsi, how='left')
    if not df_macd.empty:
        df_plot = df_plot.join(df_macd, how='left')

    # 4. 繪製圖表
    num_subplots = 1 + (1 if not df_rsi.empty else 0) + (1 if not df_macd.empty else 0)
    height_ratios = [2] + ([1] if not df_rsi.empty else []) + ([1] if not df_macd.empty else [])
    
    fig, axes = plt.subplots(num_subplots, 1, figsize=(12, 4 * num_subplots), sharex=True, gridspec_kw={'height_ratios': height_ratios})
    if num_subplots == 1: axes = [axes]
    
    curr_ax = 0
    # 子圖 1: 股價
    axes[curr_ax].plot(df_plot.index, df_plot['Close'], label='Close Price', color='blue', linewidth=2)
    axes[curr_ax].set_title(f'{SYMBOL} Daily Price & Technical Indicators (Last 30 Days)')
    axes[curr_ax].set_ylabel('Price (USD)')
    axes[curr_ax].legend(loc='upper left')
    axes[curr_ax].grid(True, alpha=0.3)
    curr_ax += 1

    # 子圖 2: RSI
    if not df_rsi.empty and 'RSI' in df_plot.columns:
        axes[curr_ax].plot(df_plot.index, df_plot['RSI'], label='RSI (14)', color='purple')
        axes[curr_ax].axhline(70, color='red', linestyle='--', alpha=0.5)
        axes[curr_ax].axhline(30, color='green', linestyle='--', alpha=0.5)
        axes[curr_ax].set_ylabel('RSI')
        axes[curr_ax].set_ylim(0, 100)
        axes[curr_ax].legend(loc='upper left')
        axes[curr_ax].grid(True, alpha=0.3)
        curr_ax += 1

    # 子圖 3: MACD
    if not df_macd.empty and 'MACD' in df_plot.columns:
        axes[curr_ax].bar(df_plot.index, df_plot['MACD_Hist'], label='MACD Hist', color='gray', alpha=0.5)
        axes[curr_ax].plot(df_plot.index, df_plot['MACD'], label='MACD', color='blue')
        axes[curr_ax].plot(df_plot.index, df_plot['MACD_Signal'], label='Signal', color='orange')
        axes[curr_ax].set_ylabel('MACD')
        axes[curr_ax].legend(loc='upper left')
        axes[curr_ax].grid(True, alpha=0.3)

    plt.xticks(rotation=45)
    plt.tight_layout()
    
    output_file = 'ccj_technical_analysis.png'
    plt.savefig(output_file, dpi=150)
    print(f"✨ 分析完成！圖表已儲存為 {output_file}")
    
    # 顯示最新數據摘要
    latest = df_plot.iloc[-1]
    print("\n" + "="*40)
    print(f"📊 {SYMBOL} 最新數據摘要 ({df_plot.index[-1].strftime('%Y-%m-%d')})")
    print("-" * 40)
    print(f"收盤價: ${latest['Close']:.2f}")
    if 'RSI' in latest:
        print(f"RSI (14): {latest['RSI']:.2f} ({'超買' if latest['RSI'] > 70 else '超賣' if latest['RSI'] < 30 else '中性'})")
    if 'MACD' in latest:
        print(f"MACD: {latest['MACD']:.4f}")
    print("="*40)

if __name__ == "__main__":
    main()
