import os
import yfinance as yf
import pandas as pd
import json
import os
from tqdm import tqdm
from datetime import datetime, timedelta
import time
# import requests_cache

class ConfigLoader:
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = self._load()


    def _load(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"❌ ERROR: Config file '{self.config_path}' not found.")
        with open(self.config_path, 'r') as file:
            return json.load(file)

    def get_strategy_params(self):
        return self.config.get("strategy", {})
        
    def get_regime_params(self):
        return self.config.get("market_regime", {})
        
    def get_capital_params(self):
        return self.config.get("capital", {})
        
    def get_paths(self):
        return self.config.get("paths", {})

    def get_data_pipeline_params(self):
        return self.config.get("data_pipeline", {})
    
    def get_backtest_params(self):
        return self.config.get("backtest", {})
    
class DataManager:
    def __init__(self, 
                 tickers, 
                 start_date, 
                 end_date, 
                 cache_filename='nifty500_master_10yr.parquet', 
                 live_mode=False):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.cache_filename = cache_filename
        self.live_mode = live_mode  
        self.prices = None
        self.benchmark_prices = None

    def fetch_benchmark(self, benchmark_ticker):
        if self.live_mode:
            print(f"📡 [LIVE MODE] Fetching real-time benchmark {benchmark_ticker}...")
            current_end_dt = pd.to_datetime(self.end_date)
            fetch_end = (current_end_dt + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            df = yf.download(benchmark_ticker, start=self.start_date, end=fetch_end, progress=False)
            print(f"Latest Date for Benchmark: {df.index[-1].strftime('%Y-%m-%d')}")
            col = 'Adj Close' if ('Adj Close' in df.columns or (isinstance(df.columns, pd.MultiIndex) and 'Adj Close' in df.columns.levels[0])) else 'Close'
            self.benchmark_prices = df[col].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df[col]
            self.benchmark_prices = self.benchmark_prices.ffill()
            return self.benchmark_prices
            
        else:
            if not os.path.exists(self.cache_filename): return None
            master_df = pd.read_parquet(self.cache_filename)
            master_df.index = pd.to_datetime(master_df.index)
            sliced_df = master_df.loc[pd.to_datetime(self.start_date):pd.to_datetime(self.end_date)]
            
            if benchmark_ticker in sliced_df.columns:
                print(f"Data found for Benchmark:{benchmark_ticker}")
                self.benchmark_prices = sliced_df[benchmark_ticker]
                return self.benchmark_prices
            else:
                print(f"Data Not found for Benchmark:{benchmark_ticker}")
                return None

    def calculate_benchmark_dma(self, window=200):
        """Calculates the Moving Average for the benchmark."""
        if hasattr(self, 'benchmark_prices') and self.benchmark_prices is not None:
            return self.benchmark_prices.rolling(window=window).mean()
        return None
    
    def calculate_benchmark_roc(self, lookback_days=63):
        """Calculates the Rate of Change (Absolute Momentum) for the benchmark."""
        if hasattr(self, 'benchmark_prices') and self.benchmark_prices is not None:
            # Calculates the fractional return over the lookback period
            self.benchmark_roc = self.benchmark_prices.pct_change(periods=lookback_days)
            return self.benchmark_roc
        return None
    
    def fetch_data(self, lookback_days=350):
        """
        Fetches pricing data using an Incremental Update (Delta Fetch) architecture.
        Loads the master Parquet, fetches only missing dates, saves, and returns the required slice.
        """
        master_df = pd.DataFrame()
        
        # 1. Load the Master Database
        if hasattr(self, 'cache_filename') and os.path.exists(self.cache_filename):
            print(f"-> Loading historical master data from {self.cache_filename}...")
            master_df = pd.read_parquet(self.cache_filename)
        
        current_end_dt = pd.to_datetime(self.end_date)
        
        # 2. Determine the Delta (Missing Dates)
        if not master_df.empty:
            last_recorded_dt = master_df.index.max()
            fetch_start = last_recorded_dt.strftime('%Y-%m-%d')
        else:
            # Fallback to a full fetch if the parquet is missing
            fetch_start = self.start_date
            last_recorded_dt = pd.to_datetime('1900-01-01') # Dummy old date
            
        # yfinance end date is exclusive, so add 1 day to ensure we get today's close
        # fetch_end = (current_end_dt + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        fetch_end = current_end_dt

        # 3. Fetch ONLY the Delta if we are behind
        if master_df.empty or last_recorded_dt.date() < current_end_dt.date():
            print(f"-> Fetching delta data from {fetch_start} to {fetch_end}...")
            
            valid_data = []
            failed_tickers = []
            
            # ==========================================
            # INCREMENTAL FETCH PIPELINE
            # ==========================================
            for ticker in tqdm(self.tickers, desc="Downloading Delta", unit="ticker"):
                try:
                    # Download individually with auto_adjust=True
                    temp_df = yf.download(ticker, 
                                          start=fetch_start, 
                                          end=fetch_end, 
                                          progress=False, 
                                          auto_adjust=True)
                    
                    if temp_df.empty:
                        failed_tickers.append(ticker)
                        continue
                        
                    # Safely extract the 'Close' column
                    if isinstance(temp_df.columns, pd.MultiIndex):
                        close_series = temp_df['Close'].iloc[:, 0].rename(ticker)
                    else:
                        close_series = temp_df['Close'].rename(ticker)
                        
                    valid_data.append(close_series)
                    
                except Exception as e:
                    failed_tickers.append(ticker)
            # ==========================================
            # Add a retry for failed tickers
            if failed_tickers:
                print(f"\n-> Cooling down API... then attempting to recover {len(failed_tickers)} failed tickers.")
                time.sleep(3)
                still_failed = []
                for ticker in tqdm(failed_tickers, desc="Retrying Casualties", unit="ticker"):
                    try:
                        time.sleep(1)
                        temp_df = yf.download(ticker, 
                                              start=fetch_start, 
                                              end=fetch_end, 
                                              progress=False, 
                                              auto_adjust=True)
                        if temp_df.empty:
                            still_failed.append(ticker)
                            continue
                        # Safely extract the 'Close' column
                        if isinstance(temp_df.columns, pd.MultiIndex):
                            close_series = temp_df['Close'].iloc[:, 0].rename(ticker)
                        else:
                            close_series = temp_df['Close'].rename(ticker)
                        
                        valid_data.append(close_series)
                    except Exception as e:
                        # If it fails a second time, it is likely a truly dead ticker or delisted stock
                        still_failed.append(ticker)
                failed_tickers = still_failed
                    
            if valid_data:
                # Combine all valid series into a single delta dataframe
                delta_df = pd.concat(valid_data, axis=1)
                delta_df.index = pd.to_datetime(delta_df.index)
                
                # 4. Combine and Deduplicate
                if not master_df.empty:
                    master_df = pd.concat([master_df, delta_df])
                    # Drop overlapping dates, keeping the most recently downloaded version
                    master_df = master_df[~master_df.index.duplicated(keep='last')]
                else:
                    master_df = delta_df
                    
                # 5. Save the updated master database back to disk for next week
                if hasattr(self, 'cache_filename'):
                    master_df.to_parquet(self.cache_filename)
                    print(f"\n✅ Master database incrementally updated and saved.")
            else:
                print("\n❌ CRITICAL ERROR: No delta data was downloaded at all.")
                
            if failed_tickers:
                print(f"⚠️ WARNING: Dropped {len(failed_tickers)} broken tickers during delta fetch.")
                print(f"Failed Tickers:{failed_tickers}")
                
        else:
            print("-> Master database is already up to date. No network fetch required.")

        # 6. Slice and Return the specific window requested by the script
        if self.live_mode:
            # For live Friday execution, we just need the trailing lookback window
            lookback_start = current_end_dt - pd.Timedelta(days=lookback_days)
            self.prices = master_df.loc[lookback_start:current_end_dt]
        else:
            # For historical backtesting, slice to the exact backtest window
            self.prices = master_df.loc[self.start_date:self.end_date]
            
        # Ensure we drop any tickers that are entirely NaN in this slice
        self.prices = self.prices.dropna(axis=1, how='all')
        
        return self.prices
    
    def calculate_rolling_high(self, lookback_days=63):
        if self.prices is None:
            raise ValueError("Prices not loaded.")
        
        # Calculates the maximum price over the rolling window
        self.rolling_highs = self.prices.rolling(window=lookback_days).max()
        return self.rolling_highs
    
    def calculate_momentum(self, lookback_days=63):
        if self.prices is None:
            raise ValueError("Prices not loaded.")
        return self.prices.pct_change(periods=lookback_days)

# 2. The Strategy Class
class MomentumStrategy:
    def __init__(self, portfolio_size=10, entry_rank=10, exit_rank=20, drawdown_limit=0.20, verbose=False):
        self.portfolio_size = portfolio_size
        self.entry_rank = entry_rank
        self.exit_rank = exit_rank
        # Defines the maximum allowed drop from the recent high (20%)
        self.drawdown_limit = drawdown_limit
        self.verbose = verbose 

    def get_target_portfolio(self, 
                             momentum_row, 
                             current_holdings, 
                             current_prices, 
                             current_highs, 
                             market_bullish=True):
        # 1. Align data and drop NaNs
        valid_scores = momentum_row.dropna()
        
        # Align prices and highs to match the valid valid_scores index
        prices_aligned = current_prices.reindex(valid_scores.index)
        highs_aligned = current_highs.reindex(valid_scores.index)
        
        # 2. PRE-FILTER: Create a mask for stocks that are strictly ABOVE the drawdown limit
        # This mathematically strips out the "beaten down" stocks before ranking
        drawdown_mask = prices_aligned > (highs_aligned * (1 - self.drawdown_limit))
        
        # Apply the mask to get only qualified, high-standing stocks
        qualified_scores = valid_scores[drawdown_mask]
        
        if self.verbose:
            print("\nMomentum Scores top 20:")
            print(qualified_scores.sort_values(ascending=False)[:20])
        
        # 3. RANKING: Rank only the qualified stocks
        ranked_tickers = qualified_scores.sort_values(ascending=False).index.tolist()
        
        top_20_pool = set(ranked_tickers[:self.exit_rank])
        top_10_pool = ranked_tickers[:self.entry_rank]
        
        target_portfolio = []
        
        # 4. EXIT RULE: (Always runs) Keep if in Top 20. 
        for ticker in current_holdings:
            if ticker in top_20_pool:
                target_portfolio.append(ticker)
        
        # 5. ENTRY RULE: (Only runs if market is > 200 DMA)
        if market_bullish:
            for ticker in top_10_pool:
                if len(target_portfolio) >= self.portfolio_size:
                    break
                    
                if ticker not in target_portfolio:
                    target_portfolio.append(ticker)
                    
        return target_portfolio
