import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

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
    end_str = data_cfg.get("master_end_date", "2026-03-09")
    history_years = data_cfg.get("master_history_years", 10)
    
    symbols_file = paths.get('symbols_file', 'symbols.csv')
    master_file = paths.get('master_data_file', 'nifty500_master_10yr.parquet')
    benchmark_ticker = regime_cfg.get('benchmark_ticker', '^CRSLDX')
    


    # 1. Load Universe
    if not os.path.exists(symbols_file):
        print(f"❌ ERROR: Cannot find {symbols_file}")
        return
        
    symbols_df = pd.read_csv(symbols_file)
    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    
    # Add benchmark to the download list so we cache that too!
    if benchmark_ticker not in universe:
        universe.append(benchmark_ticker)
        
    print(f"-> Attempting to download 10 years of data for {len(universe)} tickers...")
    
    # 2. Calculate 10-Year Date Range
    end_date = pd.to_datetime(end_str)
    start_date = end_date - pd.Timedelta(days=365 * history_years)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    # 3. Fetch from yfinance
    try:
        df = yf.download(universe, start=start_str, end=end_str, progress=True)
        
        # Extract Adjusted Close (or Close)
        if isinstance(df.columns, pd.MultiIndex):
            col = 'Adj Close' if 'Adj Close' in df.columns.levels[0] else 'Close'
            prices = df[col]
        else:
            col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            prices = df[[col]]
            
        # Clean data: Forward fill missing days, drop columns that are 100% empty
        prices = prices.ffill().dropna(axis=1, how='all')
        
        # 4. Save to Parquet
        prices.to_parquet(master_file)
        print(f"\n✅ SUCCESS: Master database saved to [{master_file}]")
        print(f"-> Total Trading Days: {len(prices)}")
        print(f"-> Total Valid Tickers: {len(prices.columns)}")
        
    except Exception as e:
        print(f"\n❌ ERROR during download: {e}")

if __name__ == "__main__":
    build_10yr_master_database()