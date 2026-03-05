import os
import yfinance as yf
import pandas as pd
import json
import os

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
    
class DataManager:
    def __init__(self, tickers, start_date, end_date, cache_filename='historical_prices.parquet'):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.cache_filename = cache_filename
        self.prices = None

    def fetch_benchmark(self, ticker='^CRSLDX'):
        """Fetches the broader market index for regime filtering."""
        print(f"Fetching benchmark data for {ticker}...")
        try:
            bench_df = yf.download(ticker, start=self.start_date, end=self.end_date, progress=False)
            
            if isinstance(bench_df.columns, pd.MultiIndex):
                col = 'Adj Close' if 'Adj Close' in bench_df.columns.levels[0] else 'Close'
                self.benchmark_prices = bench_df[col].iloc[:, 0]
            else:
                col = 'Adj Close' if 'Adj Close' in bench_df.columns else 'Close'
                self.benchmark_prices = bench_df[col]
                
            self.benchmark_prices = self.benchmark_prices.ffill()
            return self.benchmark_prices
        except Exception as e:
            print(f"Warning: Could not fetch benchmark {ticker}. Error: {e}")
            return None

    def calculate_benchmark_dma(self, window=200):
        """Calculates the Moving Average for the benchmark."""
        if hasattr(self, 'benchmark_prices') and self.benchmark_prices is not None:
            return self.benchmark_prices.rolling(window=window).mean()
        return None
    
    def fetch_data(self, force_refresh=False):
        """
        Loads data from a local cache if available. 
        If not, fetches from yfinance and saves it to the cache.
        """
        # 1. Check local cache first
        if os.path.exists(self.cache_filename) and not force_refresh:
            print(f"Loading data from local cache: [{self.cache_filename}]...")
            self.prices = pd.read_parquet(self.cache_filename)
            print(f"Loaded {len(self.prices.columns)} tickers from cache.")
            return self.prices

        # 2. Fetch from yfinance if cache doesn't exist or refresh is forced
        print(f"Fetching data from yfinance for {len(self.tickers)} tickers...")
        price_series = {}
        
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, start=self.start_date, end=self.end_date, progress=False)
                if df.empty:
                    continue
                
                # Handle both MultiIndex and Flat columns
                if isinstance(df.columns, pd.MultiIndex):
                    if 'Adj Close' in df.columns.levels[0]:
                        price_series[ticker] = df['Adj Close'].iloc[:, 0]
                    else:
                        price_series[ticker] = df['Close'].iloc[:, 0]
                else:
                    if 'Adj Close' in df.columns:
                        price_series[ticker] = df['Adj Close']
                    else:
                        price_series[ticker] = df['Close']
            except Exception:
                pass

        if not price_series:
            raise ValueError("All ticker downloads failed.")
            
        # Clean the final DataFrame
        self.prices = pd.DataFrame(price_series).ffill().dropna(axis=1, how='all')
        
        # 3. Save to local cache for future runs
        print(f"Saving fetched data to local cache: [{self.cache_filename}]...")
        self.prices.to_parquet(self.cache_filename)
        
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
    def __init__(self, portfolio_size=10, entry_rank=10, exit_rank=20, drawdown_limit=0.20):
        self.portfolio_size = portfolio_size
        self.entry_rank = entry_rank
        self.exit_rank = exit_rank
        
        # Defines the maximum allowed drop from the recent high (20%)
        self.drawdown_limit = drawdown_limit 

    def get_target_portfolio(self, momentum_row, current_holdings, current_prices, current_highs, market_bullish=True):
        valid_scores = momentum_row.dropna()
        ranked_tickers = valid_scores.sort_values(ascending=False).index.tolist()
        
        top_20_pool = set(ranked_tickers[:self.exit_rank])
        top_10_pool = ranked_tickers[:self.entry_rank]
        
        target_portfolio = []
        
        # 1. EXIT RULE: (Always runs) Keep if in Top 20 AND drop is < 20%
        for ticker in current_holdings:
            if ticker in top_20_pool:
                price = current_prices.get(ticker, 0)
                recent_high = current_highs.get(ticker, 0)
                
                if price > recent_high * (1 - self.drawdown_limit):
                    target_portfolio.append(ticker)
        
        # 2. ENTRY RULE: (Only runs if market is > 200 DMA)
        if market_bullish:
            for ticker in top_10_pool:
                if len(target_portfolio) >= self.portfolio_size:
                    break
                    
                if ticker not in target_portfolio:
                    price = current_prices.get(ticker, 0)
                    recent_high = current_highs.get(ticker, 0)
                    
                    if price > recent_high * (1 - self.drawdown_limit):
                        target_portfolio.append(ticker)
                    
        return target_portfolio
