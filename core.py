import os
import yfinance as yf
import pandas as pd
import json
import os
from tqdm import tqdm
from datetime import datetime, timedelta

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
            df = yf.download(benchmark_ticker, start=self.start_date, end=self.end_date, progress=False)
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
                self.benchmark_prices = sliced_df[benchmark_ticker]
                return self.benchmark_prices
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
    
    def fetch_data(self):
        # ==========================================
        # LIVE MODE: Fetch fresh data from internet
        # ==========================================
        if self.live_mode:
            print(f"📡 [LIVE MODE] Fetching real-time data from yfinance...")
            df = yf.download(self.tickers, start=self.start_date, end=self.end_date, progress=False)
            
            if isinstance(df.columns, pd.MultiIndex):
                col = 'Adj Close' if 'Adj Close' in df.columns.levels[0] else 'Close'
                self.prices = df[col]
            else:
                col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
                self.prices = df[[col]]
                
            self.prices = self.prices.ffill().dropna(axis=1, how='all')
            return self.prices

        # ==========================================
        # BACKTEST MODE: Slice from local database
        # ==========================================
        else:
            if not os.path.exists(self.cache_filename):
                raise FileNotFoundError(f"Master database '{self.cache_filename}' missing. Run ETL script first.")
                
            print(f"🗄️ [BACKTEST MODE] Slicing data from {self.cache_filename}...")
            master_df = pd.read_parquet(self.cache_filename)
            master_df.index = pd.to_datetime(master_df.index)
            
            start_ts = pd.to_datetime(self.start_date)
            end_ts = pd.to_datetime(self.end_date)
            
            sliced_df = master_df.loc[start_ts:end_ts]
            valid_tickers = [t for t in self.tickers if t in sliced_df.columns]
            self.prices = sliced_df[valid_tickers]
            
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
