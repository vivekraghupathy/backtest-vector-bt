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
    end_date = end_date - timedelta(days=1)
    
    data_mgr = DataManager(universe, 
                           start_date.strftime('%Y-%m-%d'), 
                           end_date.strftime('%Y-%m-%d'),
                           live_mode=True
                           )
    
    prices = data_mgr.fetch_data()
    prices = prices.ffill()
    prices = prices.dropna(how='all')
    print(prices.tail())
    momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])

    # Fetch Benchmark using config
    # bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    # bench_21dma = bench_prices.rolling(window=21).mean()
    # weekly_bench_prices = bench_prices.resample('W-FRI').last().dropna()
    # weekly_bench_roc = weekly_bench_prices.pct_change(periods=12).dropna()
    # bench_roc = data_mgr.calculate_benchmark_roc(lookback_days=regime_cfg.get('benchmark_roc_lookback', 63))
    # weekly_bench_roc = bench_roc.resample('W-FRI').last().dropna()
    # weekly_bench_prices = bench_prices.resample('W-FRI').last().dropna()
    # weekly_bench_21dma = bench_21dma.resample('W-FRI').last().dropna()
    latest_momentum = momentum_df.iloc[-1]
    latest_prices = prices.iloc[-1]
    latest_highs = rolling_highs_df.iloc[-1]
    affordable_tickers = latest_prices[latest_prices <= allocation_per_slot].index
    latest_momentum = latest_momentum.reindex(affordable_tickers).dropna()
    is_bull_market = True  # Default assumption
    # if weekly_bench_21dma is not None and weekly_bench_prices is not None:
    #     try:
    #         current_price = weekly_bench_prices.iloc[-1]
    #         current_21dma = weekly_bench_21dma.iloc[-1]
    
    #         prev_price = weekly_bench_prices.iloc[-2]
    #         prev_21dma = weekly_bench_21dma.iloc[-2]
    #         if current_price < current_21dma and prev_price < prev_21dma:
    #             is_bull_market = False
    #     except Exception:
    #         is_bull_market = True
    # if len(weekly_bench_roc) >= 2:
    #     curr_roc = weekly_bench_roc.iloc[-1]
    #     prev_roc = weekly_bench_roc.iloc[-2]
    #     is_bear_market = (curr_roc < 0) and (prev_roc < 0)
    #     is_bull_market = not is_bear_market
    # else:
    #     # Fallback if there is barely any data
    #     curr_roc = weekly_bench_roc.iloc[-1]
    #     prev_roc = 0.0
    #     is_bull_market = curr_roc >= 0

    liquidate_on_bear = regime_cfg.get('liquidate_on_bear_market', False)

    strategy = MomentumStrategy(
        portfolio_size=strat_cfg['portfolio_size'],
        entry_rank=strat_cfg['entry_rank'],
        exit_rank=strat_cfg['exit_rank'],
        drawdown_limit=strat_cfg['drawdown_limit'],
        verbose=True
    )
    
    if is_bull_market:
        target_portfolio = strategy.get_target_portfolio(latest_momentum,
                                                        current_tickers, 
                                                        latest_prices, 
                                                        latest_highs,
                                                        market_bullish=is_bull_market)
    else:
        if liquidate_on_bear:
            print("🔴 STATUS: BEARISH (MACRO FLUSH). 2-Week negative confirmation met.")
            print("   Liquidate all positions.")
            print("   Allocate 50% in GOLDCASE & 50% in LIQUIDCASE")
            target_portfolio = []
        else:
            print("🔴 STATUS: BEARISH. 2-Week negative confirmation met.")
            print("   Buying is HALTED. Only trailing stop exits will be processed.")
            target_portfolio = strategy.get_target_portfolio(latest_momentum,
                                                        current_tickers, 
                                                        latest_prices, 
                                                        latest_highs,
                                                        market_bullish=is_bull_market)
    print("="*60)
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