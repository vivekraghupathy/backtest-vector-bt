import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
from tqdm import tqdm
# Import your ConfigLoader
from core import ConfigLoader

def build_10yr_master_database():
    print("===================================================")
    print("      BUILDING 10-YEAR MASTER LOCAL DATABASE       ")
    print("===================================================")
    
    cfg = ConfigLoader('config.json')
    paths = cfg.get_paths()
    regime_cfg = cfg.get_regime_params()
    data_cfg = cfg.get_data_pipeline_params()
    end_str = data_cfg.get("master_end_date", "2026-03-31")
    history_years = data_cfg.get("master_history_years", 10)
    
    symbols_file = paths.get('symbols_file', 'symbols.csv')
    master_file = paths.get('master_data_file', 'nifty500_master_10yr.parquet')
    benchmark_ticker = regime_cfg.get('benchmark_ticker', '^CRSLDX')
    gold_etf_ticker = regime_cfg.get('gold_etf_ticker', 'SBIGETS.NS')
    vix_ticker = regime_cfg.get('vix_ticker', '^INDIAVIX')


    # 1. Load Universe
    if not os.path.exists(symbols_file):
        print(f"❌ ERROR: Cannot find {symbols_file}")
        return
        
    symbols_df = pd.read_csv(symbols_file)
    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    
    # Add benchmark to the download list so we cache that too!
    if benchmark_ticker not in universe:
        universe.append(benchmark_ticker)
        universe.append(gold_etf_ticker)
        
    print(f"-> Attempting to download 10 years of data for {len(universe)} tickers...")
    
    # 2. Calculate 10-Year Date Range
    end_date = pd.to_datetime(end_str)
    start_date = end_date - pd.Timedelta(days=365 * history_years)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    # 3. Fetch from yfinance
    valid_data = []
    failed_tickers = []
    for ticker in tqdm(universe, desc="Downloading Tickers", unit="ticker"):
        try:
            # Download individually with auto_adjust=True (Fixes the warning)
            temp_df = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=True)
            
            # If Yahoo returns an empty dataframe for this ticker, skip it
            if temp_df.empty:
                failed_tickers.append(ticker)
                continue
                
            # Safely extract the 'Close' column
            # Single ticker downloads usually return flat columns, but we check just in case yfinance changes
            if isinstance(temp_df.columns, pd.MultiIndex):
                close_series = temp_df['Close'].iloc[:, 0].rename(ticker)
            else:
                close_series = temp_df['Close'].rename(ticker)
                
            valid_data.append(close_series)
            
        except Exception as e:
            # If the NoneType error or any other exception happens, trap it here
            failed_tickers.append(ticker)
            
    # --- ASSEMBLE AND SAVE THE MASTER DATABASE ---
    if valid_data:
        try:
            # Concatenate all individual valid series into one master DataFrame
            prices = pd.concat(valid_data, axis=1)
            
            # Ensure the index is a standard pandas datetime index
            prices.index = pd.to_datetime(prices.index)
            
            # Clean data: Forward fill missing days, drop columns that are 100% empty
            prices = prices.ffill().dropna(axis=1, how='all')
            
            # Save to Parquet
            prices.to_parquet(master_file)
            print(f"\n✅ SUCCESS: Master database saved to [{master_file}]")
            print(f"-> Total Trading Days: {len(prices)}")
            print(f"-> Total Valid Tickers: {len(prices.columns)}")
            
        except Exception as e:
            print(f"\n❌ ERROR during data compilation or Parquet save: {e}")
    else:
        print("\n❌ CRITICAL ERROR: No data was downloaded at all. Parquet file not created.")
        
    # Log the casualties so you know who is missing
    if failed_tickers:
        print(f"\n⚠️ WARNING: Dropped {len(failed_tickers)} broken tickers from Yahoo Finance.")
        # print("Failed Tickers:", failed_tickers) # Uncomment this if you want to see the exact list   

if __name__ == "__main__":
    build_10yr_master_database()