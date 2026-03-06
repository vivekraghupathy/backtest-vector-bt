
import matplotlib.pyplot as plt
import pandas as pd
import math
from core import DataManager, MomentumStrategy, ConfigLoader

class SimplePortfolio:
    def __init__(self, allocation_per_slot=100000):
        # E.g., 1 Lakh INR dedicated to each of the 10 slots
        self.allocation_per_slot = allocation_per_slot 
        self.positions = {}  # Format: {ticker: number_of_shares}
        
        # Total starting capital = 10 slots * allocation
        self.cash = allocation_per_slot * 10 
        self.initial_capital = self.cash
        self.equity_history = []
        self.total_trades = 0

    def update_portfolio(self, date, target_tickers, current_prices):
        """
        Sells dropped stocks completely. 
        Buys new stocks with a fixed INR allocation.
        Ignores existing stocks (lets them ride).
        """
        # 1. SELL PHASE: Complete liquidation of stocks no longer in target
        current_tickers = list(self.positions.keys())
        for ticker in current_tickers:
            if ticker not in target_tickers:
                shares_held = self.positions.pop(ticker)
                price = current_prices.get(ticker)
                
                if pd.notna(price):
                    self.cash += shares_held * price
                    self.total_trades += 1

        # 2. BUY PHASE: Allocate fixed INR to brand new entries only
        for ticker in target_tickers:
            if ticker not in self.positions:
                price = current_prices.get(ticker)
                
                if pd.notna(price) and price > 0:
                    # Calculate how many shares the fixed slot allocation can buy
                    shares_to_buy = math.floor(self.allocation_per_slot / price)
                    cost = shares_to_buy * price
                    
                    if self.cash >= cost:
                        self.cash -= cost
                        self.positions[ticker] = shares_to_buy

        # 3. LOGGING: Calculate total current equity
        positions_value = sum(
            self.positions[t] * current_prices.get(t, 0) 
            for t in self.positions
        )
        total_equity = self.cash + positions_value
        
        self.equity_history.append({
            'Date': date,
            'Total Equity': total_equity,
            'Cash': self.cash,
            'Invested Value': positions_value,
            'Active Positions': len(self.positions)
        })

    def get_equity_curve(self):
        df = pd.DataFrame(self.equity_history)
        if not df.empty:
            df.set_index('Date', inplace=True)
        return df
    

def plot_backtest_results(results_df):
    """
    Generates a two-panel plot showing Total Equity growth and Cash drag over time.
    """
    # Use a clean, professional style
    plt.style.use('seaborn-v0_8-darkgrid')
    
    # Ensure the index is in datetime format for proper plotting
    results_df.index = pd.to_datetime(results_df.index)
    
    # Create a figure with 2 subplots (Equity on top, Cash on bottom)
    # gridspec_kw makes the top plot 3x taller than the bottom one
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                   gridspec_kw={'height_ratios': [3, 1]}, 
                                   sharex=True)
    
    # --- Top Subplot: Total Equity ---
    ax1.plot(results_df.index, results_df['Total Equity'], 
             label='Total Portfolio Value', color='#1f77b4', linewidth=2)
    ax1.set_title('Momentum Strategy (Top 10 Entry / Top 20 Exit)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Equity (₹)', fontsize=12)
    
    # Format the y-axis to show commas for millions/lakhs
    ax1.yaxis.set_major_formatter(plt.matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
    ax1.legend(loc='upper left')
    
    # --- Bottom Subplot: Cash Balance ---
    # Using a filled area makes it easy to visualize periods of high cash (low market participation)
    ax2.fill_between(results_df.index, 0, results_df['Cash'], 
                     label='Uninvested Cash', color='#7f7f7f', alpha=0.3)
    ax2.plot(results_df.index, results_df['Cash'], color='#7f7f7f', linewidth=1)
    
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Cash (₹)', fontsize=12)
    ax2.yaxis.set_major_formatter(plt.matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
    ax2.legend(loc='upper left')
    
    # Clean up layout and display
    plt.tight_layout()
    plt.show()

def print_run_summary(results_df, total_trades, initial_capital):
    """Calculates and prints key performance metrics from the equity curve."""
    
    # 1. Total Gain %
    final_equity = results_df['Total Equity'].iloc[-1]
    total_gain_pct = ((final_equity - initial_capital) / initial_capital) * 100
    
    # 2. Max Gain % (Peak equity compared to initial capital)
    max_equity = results_df['Total Equity'].max()
    max_gain_pct = ((max_equity - initial_capital) / initial_capital) * 100
    
    # 3. Max Loss (Maximum Drawdown)
    # Calculate the running maximum (peak) at each point in time
    results_df['Peak_Equity'] = results_df['Total Equity'].cummax()
    # Calculate the percentage drop from the running peak
    results_df['Drawdown_Pct'] = ((results_df['Total Equity'] - results_df['Peak_Equity']) / results_df['Peak_Equity']) * 100
    # The lowest point in the drawdown curve is our Max Drawdown
    max_loss_pct = results_df['Drawdown_Pct'].min() 
    
    print("\n" + "="*40)
    print("        BACKTEST RUN SUMMARY")
    print("="*40)
    print(f"Initial Capital   : ₹{initial_capital:,.2f}")
    print(f"Final Equity      : ₹{final_equity:,.2f}")
    print(f"Total Trades      : {total_trades}")
    print("-" * 40)
    print(f"Total Gain        : {total_gain_pct:.2f}%")
    print(f"Max Gain (Peak)   : {max_gain_pct:.2f}%")
    print(f"Max Loss (DD)     : {max_loss_pct:.2f}%")
    print("="*40 + "\n")


def run_backtest():
    # Define a universe 
    print("--- Starting Backtest Engine ---")
    
    # 1. Load Configuration
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    
    # Load Universe
    try:
        symbols_df = pd.read_csv(paths['symbols_file'])
        universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    except FileNotFoundError:
        print(f"❌ ERROR: '{paths['symbols_file']}' not found.")
        return
    
    # Initialize components
    # universe = universe[:100]  # Limit to top 100 tickers for faster backtest runs
    data_mgr = DataManager(universe, '2024-01-01', '2026-02-28', cache_filename=paths['cache_file'])
    strategy = MomentumStrategy(
        portfolio_size=strat_cfg['portfolio_size'],
        entry_rank=strat_cfg['entry_rank'],
        exit_rank=strat_cfg['exit_rank'],
        drawdown_limit=strat_cfg['drawdown_limit']
    )
    portfolio = SimplePortfolio(allocation_per_slot=cap_cfg['allocation_per_slot'])
    
    # Prepare Data
    prices = data_mgr.fetch_data(force_refresh=False)
    momentum_df = data_mgr.calculate_momentum(lookback_days=63)
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=63)

    bench_prices = data_mgr.fetch_benchmark('^CRSLDX')
    bench_200_dma = data_mgr.calculate_benchmark_dma(window=200)

    # Resample to Week-End for rebalancing, dropping initial NaN rows
    monthly_momentum = momentum_df.resample('W-FRI').last().dropna(how='all')
    
    print("\n--- Running Time-Series Loop ---")
    for date, momentum_row in monthly_momentum.iterrows():
        # Get exact prices for this rebalance date
        # Use exact match or the closest previous trading day if month-end fell on a holiday
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]
        latest_bench_price = bench_prices.loc[:date].iloc[-1]
        latest_bench_dma = bench_200_dma.loc[:date].iloc[-1]
        is_bull_market = latest_bench_price > latest_bench_dma

        current_holdings = list(portfolio.positions.keys())  
        # 1. Strategy decides what to hold
        target_portfolio = strategy.get_target_portfolio(
            momentum_row, 
            current_holdings, 
            current_prices, 
            current_highs,
            market_bullish=is_bull_market)
        
        # 2. Portfolio executes the trades
        portfolio.update_portfolio(date, target_portfolio, current_prices)
        
       #print portfolio status at each rebalance
        print(f"Date: {date.date()} \n Target Portfolio: {target_portfolio} \n Cash: ₹{portfolio.cash:,.2f} \n Total Equity: ₹{portfolio.equity_history[-1]['Total Equity']:,.2f}")

    print(f"\nTotal Trades Executed: {portfolio.total_trades}")
    print("\n--- Backtest Complete ---")
    
    # Extract results
    results_df = portfolio.get_equity_curve()
    print_run_summary(results_df, portfolio.total_trades, portfolio.initial_capital)  
    return results_df

if __name__ == "__main__":
    results = run_backtest()
    plot_backtest_results(results)
