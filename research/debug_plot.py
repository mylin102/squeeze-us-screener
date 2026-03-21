import pandas as pd
import yfinance as yf
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from squeeze.report.visualizer import plot_ticker

def main():
    print("Downloading AMZN data...")
    df = yf.download('AMZN', period='1y', interval='1d')
    
    # Selection logic for yfinance newer versions
    if isinstance(df.columns, pd.MultiIndex) and 'AMZN' in df.columns.get_level_values(0):
        df_selected = df['AMZN']
    else:
        df_selected = df

    print("Data start date:", df_selected.index[0])
    print("Data end date:", df_selected.index[-1])
    print("Data rows:", len(df_selected))

    output_path = 'debug_amzn.png'
    print(f"Plotting to {output_path}...")
    plot_ticker(df_selected, 'AMZN', output_path)
    
    if os.path.exists(output_path):
        print(f"File size: {os.path.getsize(output_path)} bytes")
    else:
        print("File was not created!")

if __name__ == "__main__":
    main()
