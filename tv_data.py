import pandas as pd
import time
from tqdm import tqdm
from tvDatafeed import TvDatafeed, Interval

class TradingViewManager:
    def __init__(self, tickers, n_bars=63):
        """
        Initializes the TV engine.
        n_bars defaults to 63 (approx 3 months of trading days) to ensure we 
        have enough data for a clean 60-day momentum calculation.
        """
        self.tickers = tickers
        self.n_bars = n_bars
        print("-> Initializing TradingView connection (Anonymous)...")
        self.tv = TvDatafeed()

    def fetch_live_data(self):
        """
        Fetches the recent rolling window for the live weekly rebalance.
        Includes mandatory rate-limit delays.
        """
        valid_data = []
        failed_tickers = []
        
        print(f"\n-> Fetching {self.n_bars} days of live data from TradingView...")
        
        for ticker in tqdm(self.tickers, desc="TV Live Sync", unit="ticker"):
            try:
                # 1. Clean the ticker (Remove '.NS' if it exists)
                clean_ticker = ticker.replace('.NS', '')
                
                # 2. Fetch the data
                tv_data = self.tv.get_hist(
                    symbol=clean_ticker, 
                    exchange='NSE', 
                    interval=Interval.in_daily, 
                    n_bars=self.n_bars
                )
                
                if tv_data is None or tv_data.empty:
                    failed_tickers.append(ticker)
                    continue
                
                # 3. Extract Close price and rename back to standard 'TICKER.NS' format
                close_series = tv_data['close'].rename(ticker)
                valid_data.append(close_series)
                
            except Exception as e:
                failed_tickers.append(ticker)
                
            # CRITICAL: 1-second delay to prevent IP ban from TradingView
            time.sleep(1)
            
        # --- ASSEMBLE ---
        if valid_data:
            live_df = pd.concat(valid_data, axis=1)
            # Normalize index to pure dates to match yfinance format perfectly
            live_df.index = pd.to_datetime(live_df.index).normalize()
            
            # Forward fill any random missing intraday gaps, then drop empty columns
            live_df = live_df.ffill().dropna(axis=1, how='all')
            
            if failed_tickers:
                print(f"\n⚠️ TV Warning: {len(failed_tickers)} tickers failed or delisted.")
                
            return live_df
        else:
            raise ValueError("❌ CRITICAL ERROR: TradingView returned no data.")