import os
import pandas as pd
import math
from datetime import datetime, timedelta

# Import your shared brain
from core import DataManager, MomentumStrategy, ConfigLoader

# ==========================================
# FILE MANAGEMENT FUNCTIONS
# ==========================================
def load_current_positions(filepath='current_holdings.csv'):
    if not os.path.exists(filepath):
        pd.DataFrame(columns=['Ticker', 'Shares']).to_csv(filepath, index=False)
        return {}
    df = pd.read_csv(filepath)
    if df.empty: return {}
    return dict(zip(df['Ticker'], df['Shares']))

def save_new_positions(new_positions, filepath='current_holdings.csv'):
    df = pd.DataFrame(list(new_positions.items()), columns=['Ticker', 'Shares'])
    df.to_csv(filepath, index=False)
    print(f"✅ State Updated: [{filepath}]")

def append_to_journal(trades, filepath='trading_journal.csv'):
    """Appends executed BUY/SELL orders to the transaction ledger."""
    if not trades: return
    
    df = pd.DataFrame(trades)
    # If file doesn't exist, write with header. Otherwise, append without header.
    if not os.path.exists(filepath):
        df.to_csv(filepath, index=False)
    else:
        df.to_csv(filepath, mode='a', header=False, index=False)
    print(f"✅ Journal Updated: [{filepath}]")

def snapshot_holdings(date_str, holdings, prices, filepath='holdings_history.csv'):
    """Records the exact portfolio state and valuations for the current date."""
    if not holdings: return
    
    snapshot = []
    for ticker, shares in holdings.items():
        price = prices.get(ticker, 0)
        snapshot.append({
            'Date': date_str,
            'Ticker': ticker,
            'Shares': shares,
            'Closing_Price': round(price, 2),
            'Total_Value': round(shares * price, 2)
        })
        
    df = pd.DataFrame(snapshot)
    if not os.path.exists(filepath):
        df.to_csv(filepath, index=False)
    else:
        df.to_csv(filepath, mode='a', header=False, index=False)
    print(f"✅ Snapshot Saved: [{filepath}]")


# ==========================================
# MAIN EXECUTION
# ==========================================
def generate_weekly_signals(allocation_per_slot=100000,force_refresh=False):

    # 🔴 1. LOAD CONFIGURATION
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()

    run_date = datetime.now().strftime('%Y-%m-%d')
    print(f"--- Generating Live Signals for {run_date} ---")
    if not force_refresh:
        print("!!!WARNING!!! Using cached data rebalance may be inaccurate.")
    
    try:
        symbols_df = pd.read_csv(paths['symbols_file'])
        universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    except FileNotFoundError:
        print(f"❌ ERROR: '{paths['symbols_file']}' not found.")
        return

    current_positions = load_current_positions(paths['holdings_file'])
    current_tickers = list(current_positions.keys())
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
    
    data_mgr = DataManager(universe, 
                           start_date.strftime('%Y-%m-%d'), 
                           end_date.strftime('%Y-%m-%d'))
    prices = data_mgr.fetch_data(force_refresh=force_refresh)
    momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])

    # Fetch Benchmark using config
    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    bench_dma = data_mgr.calculate_benchmark_dma(window=regime_cfg['benchmark_dma_window'])

    latest_momentum = momentum_df.iloc[-1]
    latest_prices = prices.iloc[-1]
    latest_highs = rolling_highs_df.iloc[-1]

    latest_bench_price = bench_prices.iloc[-1]
    latest_bench_dma = bench_dma.iloc[-1]
    is_bull_market = latest_bench_price > latest_bench_dma

    print("\n" + "="*50)
    print(f"MARKET REGIME: {regime_cfg['benchmark_ticker']} is at {latest_bench_price:.2f} ({regime_cfg['benchmark_dma_window']} DMA: {latest_bench_dma:.2f})")
    if is_bull_market:
        print("🟢 BULLISH: Buying is ENABLED.")
    else:
        print("🔴 BEARISH: Buying is HALTED. Only exits will be processed.")
    print("="*50)

    strategy = MomentumStrategy(
        portfolio_size=strat_cfg['portfolio_size'],
        entry_rank=strat_cfg['entry_rank'],
        exit_rank=strat_cfg['exit_rank'],
        drawdown_limit=strat_cfg['drawdown_limit'],
        verbose=True
    )
    
    target_portfolio = strategy.get_target_portfolio(latest_momentum,
                                                     current_tickers, 
                                                     latest_prices, 
                                                     latest_highs,
                                                     market_bullish=is_bull_market)
    
    # Trackers for the current state and ledger
    new_positions = {}
    executed_trades = []
    
    sells = [t for t in current_tickers if t not in target_portfolio]
    buys = [t for t in target_portfolio if t not in current_tickers]
    holds = [t for t in current_tickers if t in target_portfolio]
    
    print("\n" + "="*50)
    print("               ACTION REQUIRED")
    print("="*50)
    
    # --- PROCESS SELLS ---
    if sells:
        print("\n🔴 SELL (Liquidate completely):")
        for ticker in sells:
            shares = current_positions[ticker]
            price = latest_prices.get(ticker, 0)
            print(f"   -> {ticker}: Sell all {shares} shares (Last Price: ₹{price:.2f})")
            
            # Log the trade
            executed_trades.append({
                'Date': run_date, 'Action': 'SELL', 'Ticker': ticker,
                'Shares': shares, 'Execution_Price': round(price, 2),
                'Total_Amount': round(shares * price, 2)
            })
    else:
        print("\n🔴 SELL: None")

    # --- PROCESS BUYS ---
    if buys:
        print(f"\n🟢 BUY (Target: ₹{allocation_per_slot:,.0f} each):")
        for ticker in buys:
            price = latest_prices.get(ticker, 0)
            if pd.notna(price) and price > 0:
                shares = math.floor(allocation_per_slot / price)
                cost = shares * price
                print(f"   -> {ticker}: Buy {shares} shares @ ~₹{price:.2f} (Total: ₹{cost:,.2f})")
                
                new_positions[ticker] = shares
                # Log the trade
                executed_trades.append({
                    'Date': run_date, 'Action': 'BUY', 'Ticker': ticker,
                    'Shares': shares, 'Execution_Price': round(price, 2),
                    'Total_Amount': round(cost, 2)
                })
    else:
        print("\n🟢 BUY: None")

    # --- PROCESS HOLDS ---
    print(f"\n🔵 HOLD ({len(holds)} existing positions):")
    for ticker in holds:
         shares = current_positions[ticker]
         print(f"   -> {ticker}: {shares} shares")
         new_positions[ticker] = shares
         
    print("="*50)
    if not force_refresh:
        print("!!!WARNING!!! Using cached data rebalance may be inaccurate.")
    # --- CONFIRMATION & LOGGING ---
    if buys or sells:
        print("\n⚠️ WARNING: Only proceed if you have successfully placed all orders in your broker account.")
        confirmation = input("Did you execute these trades perfectly? Type 'y' to update logs or 'n' to cancel: ").strip().lower()
        
        if confirmation == 'y':
            save_new_positions(new_positions)
            append_to_journal(executed_trades)
            # snapshot_holdings(run_date, new_positions, latest_prices)
        else:
            print("\n❌ CANCELED: Logs were NOT updated.")
    else:
        print("\n✅ No trades required today.")

if __name__ == "__main__":
    generate_weekly_signals(allocation_per_slot=25000, force_refresh=False)