
import matplotlib.pyplot as plt
import pandas as pd
import math
from core import DataManager, MomentumStrategy, ConfigLoader

class SimplePortfolio:
    def __init__(self, allocation_per_slot, initial_capital=1000000, liquid_yield=0.065):
        self.allocation_per_slot = allocation_per_slot
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}          # Dictionary of {ticker: shares}
        self.total_trades = 0
        self.equity_history = []            # To store equity curve data
        self.liquid_yield = liquid_yield
        self.last_date = None

    def update_portfolio(self, date, target_tickers, current_prices):
        """
        Sells dropped stocks completely. 
        Buys new stocks with a fixed INR allocation.
        Ignores existing stocks (lets them ride).
        """
        #Add interest on uninvested cash for the days passed since last rebalance
        if self.last_date is not None:
            days_passed = (date - self.last_date).days
            if days_passed > 0:
                # Calculate simple interest for the days passed
                interest = self.cash * (self.liquid_yield * (days_passed / 365.0))
                self.cash += interest
                # print(f"📈 Added interest of ₹{interest:,.2f} for {days_passed} days. New Cash Balance: ₹{self.cash:,.2f}")
                
        self.last_date = date

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

def print_run_summary(results_df, 
                      total_trades, 
                      initial_capital, 
                      start_date, 
                      end_date, 
                      bench_series=None, 
                      bench_ticker="Benchmark"):
    """Calculates and prints the final backtest metrics vs Benchmark."""
    if results_df.empty:
        print("❌ No trades executed during this period.")
        return

    # 1. Strategy Metrics
    equity_curve = results_df['Total Equity']
    final_equity = equity_curve.iloc[-1]
    strat_abs_return = ((final_equity - initial_capital) / initial_capital) * 100
    
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    years = (end_dt - start_dt).days / 365.25
    strat_cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # Calculate Strategy Max Drawdown
    rolling_max_strat = equity_curve.cummax()
    drawdown_strat = (equity_curve - rolling_max_strat) / rolling_max_strat
    max_dd_strat = drawdown_strat.min() * 100  # Will be a negative percentage

    # 2. Benchmark Metrics
    if bench_series is not None and not bench_series.empty:
        bench_start = bench_series.iloc[0]
        bench_end = bench_series.iloc[-1]
        bench_abs_return = ((bench_end - bench_start) / bench_start) * 100
        bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
        
        # Calculate Benchmark Max Drawdown
        rolling_max_bench = bench_series.cummax()
        drawdown_bench = (bench_series - rolling_max_bench) / rolling_max_bench
        max_dd_bench = drawdown_bench.min() * 100
    else:
        bench_abs_return, bench_cagr, max_dd_bench = 0.0, 0.0, 0.0

    # 3. Print the Output Table
    print("\n" + "="*60)
    print(f"📊 BACKTEST SUMMARY: {start_date} to {end_date}")
    print("="*60)
    print(f"Initial Capital:   ₹{initial_capital:,.2f}")
    print(f"Final Equity:      ₹{final_equity:,.2f}")
    print(f"Total Trades:      {total_trades}")
    print("-" * 60)
    print(f"PERFORMANCE        | Strategy         | Benchmark ({bench_ticker})")
    print("-" * 60)
    print(f"Absolute Return    | {strat_abs_return:>8.2f}%       | {bench_abs_return:>8.2f}%")
    print(f"CAGR               | {strat_cagr:>8.2f}%       | {bench_cagr:>8.2f}%")
    print(f"Max Drawdown       | {max_dd_strat:>8.2f}%       | {max_dd_bench:>8.2f}%")
    
    # Calculate Alpha (Outperformance)
    alpha = strat_cagr - bench_cagr
    print("-" * 60)
    print(f"ALPHA (CAGR Diff)  | [ {alpha:+.2f}% ]")
    print("="*60 + "\n")


def run_backtest():
    # Define a universe 
    print("--- Starting Backtest Engine ---")
    
    # 1. Load Configuration
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    
    bt_cfg = cfg.get_backtest_params()
    bt_start = bt_cfg.get("start_date", "2018-01-01")
    bt_end = bt_cfg.get("end_date", "2024-01-01")
    # Load Universe
    try:
        symbols_df = pd.read_csv(paths['symbols_file'])
        universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    except FileNotFoundError:
        print(f"❌ ERROR: '{paths['symbols_file']}' not found.")
        return
    
    # Initialize components
    data_mgr = DataManager(
        universe, 
        start_date=bt_start, 
        end_date=bt_end, 
        cache_filename=paths['master_data_file'],
        live_mode=False
    )

    strategy = MomentumStrategy(
        portfolio_size=strat_cfg['portfolio_size'],
        entry_rank=strat_cfg['entry_rank'],
        exit_rank=strat_cfg['exit_rank'],
        drawdown_limit=strat_cfg['drawdown_limit']
    )
    total_initial_capital = cap_cfg['allocation_per_slot'] * strat_cfg['portfolio_size']

    portfolio = SimplePortfolio(
        allocation_per_slot=cap_cfg['allocation_per_slot'],
        initial_capital=total_initial_capital,
        liquid_yield=cap_cfg.get('liquid_etf_yield', 0.065)
    )
    
    # Prepare Data
    prices = data_mgr.fetch_data()
    momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])


    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    bench_roc = data_mgr.calculate_benchmark_roc(lookback_days=regime_cfg.get('benchmark_roc_lookback', 63))
    
    if bench_roc is not None:
        weekly_bench_roc = bench_roc.resample('W-FRI').last().dropna()
    else:
        weekly_bench_roc = None

    # Resample to Week-End for rebalancing, dropping initial NaN rows
    monthly_momentum = momentum_df.resample('W-FRI').last().dropna(how='all')
    
    print("\n--- Running Time-Series Loop ---")
    for date, momentum_row in monthly_momentum.iterrows():
        # Get exact prices for this rebalance date
        # Use exact match or the closest previous trading day if month-end fell on a holiday
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]

        if weekly_bench_roc is not None:
            past_roc_slice = weekly_bench_roc.loc[:date]
                
            if len(past_roc_slice) >= 2:
                curr_roc = past_roc_slice.iloc[-1]
                prev_roc = past_roc_slice.iloc[-2]
                
                # A Bear Market requires TWO consecutive weeks of negative ROC
                is_bear_market = (curr_roc < 0) and (prev_roc < 0)
                is_bull_market = not is_bear_market
                
            elif len(past_roc_slice) == 1:
                is_bull_market = past_roc_slice.iloc[-1] >= 0
            else:
                is_bull_market = True 
        else:
                is_bull_market = True

        liquidate_on_bear = regime_cfg.get('liquidate_on_bear_market', False)

        current_holdings = list(portfolio.positions.keys())  
        # 1. Strategy decides what to hold
        if not is_bull_market and liquidate_on_bear:
            target_portfolio = []  # Force complete liquidation in bear market if configured
        else:   
            target_portfolio = strategy.get_target_portfolio(
                momentum_row, 
                current_holdings, 
                current_prices, 
                current_highs,
                market_bullish=is_bull_market)
        
        # 2. Portfolio executes the trades
        portfolio.update_portfolio(date, target_portfolio, current_prices)
        
       #print portfolio status at each rebalance
       #print(f"Date: {date.date()} \n Target Portfolio: {target_portfolio} \n Cash: ₹{portfolio.cash:,.2f} \n Total Equity: ₹{portfolio.equity_history[-1]['Total Equity']:,.2f}")

    print(f"\nTotal Trades Executed: {portfolio.total_trades}")
    print("\n--- Backtest Complete ---")
    
    # Extract results
    results_df = portfolio.get_equity_curve()
    total_initial_capital = cap_cfg['allocation_per_slot'] * strat_cfg['portfolio_size']

    sliced_bench = None
    if bench_prices is not None and not bench_prices.empty:
        sliced_bench = bench_prices.loc[bt_start:bt_end].dropna()
 
    print_run_summary(
        results_df=results_df, 
        total_trades=portfolio.total_trades, 
        initial_capital=total_initial_capital, 
        start_date=bt_start, 
        end_date=bt_end,
        bench_series=sliced_bench,                          
        bench_ticker=regime_cfg['benchmark_ticker']         
    )

    return results_df

if __name__ == "__main__":
    results = run_backtest()
    plot_backtest_results(results)
