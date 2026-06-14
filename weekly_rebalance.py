import os
import pandas as pd
import math
from datetime import datetime, timedelta
import yfinance as yf

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
def generate_weekly_signals(force_refresh=False):

    # 🔴 1. LOAD CONFIGURATION
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    barbell_cfg = cfg.get_barbell_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()

    print("\nSelect Strategy to Rebalance:")
    print("1. Momentum Strategy (Default)")
    print("2. Barbell Strategy")
    choice = input("Enter choice [1 or 2]: ").strip()
    is_barbell = (choice == "2")

    run_date = datetime.now().strftime('%Y-%m-%d')
    strategy_name = "Barbell Strategy" if is_barbell else "Momentum Strategy"
    print(f"\n--- Generating Live Signals for {strategy_name} ({run_date}) ---")
    
    # Select configuration and paths
    if is_barbell:
        holdings_file = paths.get('barbell_holdings_file', 'barbell_holdings.csv')
        journal_file = paths.get('barbell_journal_file', 'barbell_trading_journal.csv')
        history_file = paths.get('barbell_history_file', 'barbell_holdings_history.csv')
        
        portfolio_size = barbell_cfg.get('risk_portfolio_size', 5)
        entry_rank = barbell_cfg.get('entry_rank', 5)
        exit_rank = barbell_cfg.get('exit_rank', 25)
        drawdown_limit = barbell_cfg.get('drawdown_limit', 0.10)
        lookback_days = barbell_cfg.get('momentum_lookback_days', 60)
        skip_latest_period = barbell_cfg.get('skip_latest_period', False)
        
        safe_weight_bull = barbell_cfg.get('safe_weight_bull', 0.30)
        safe_weight_bear = barbell_cfg.get('safe_weight_bear', 0.80)
        gold_ratio_in_safe = barbell_cfg.get('gold_ratio_in_safe', 0.50)
    else:
        holdings_file = paths.get('holdings_file', 'current_holdings.csv')
        journal_file = paths.get('journal_file', 'trading_journal.csv')
        history_file = paths.get('history_file', 'holdings_history.csv')
        
        portfolio_size = strat_cfg['portfolio_size']
        entry_rank = strat_cfg['entry_rank']
        exit_rank = strat_cfg['exit_rank']
        drawdown_limit = strat_cfg['drawdown_limit']
        lookback_days = strat_cfg['momentum_lookback_days']
        skip_latest_period = strat_cfg.get('skip_latest_period', False)

    try:
        symbols_df = pd.read_csv(paths['symbols_file'])
        universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    except FileNotFoundError:
        print(f"❌ ERROR: '{paths['symbols_file']}' not found.")
        return

    current_positions = load_current_positions(holdings_file)
    current_tickers = [t for t in current_positions.keys() if t != 'GOLDBEES.NS']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
    
    data_mgr = DataManager(universe, 
                           start_date.strftime('%Y-%m-%d'), 
                           end_date.strftime('%Y-%m-%d'),
                           live_mode=True
                           )
    
    prices = data_mgr.fetch_data()
    prices = prices.ffill().dropna(how='all')
    latest_prices = prices.iloc[-1]
    
    # Fetch Gold price if barbell strategy
    latest_gold_price = 0.0
    is_gold_bullish = True
    if is_barbell:
        try:
            print("📡 Fetching Gold ETF (GOLDBEES.NS) price and trend...")
            gold_df = yf.download("GOLDBEES.NS", period="1y", progress=False)
            col = 'Adj Close' if 'Adj Close' in gold_df.columns else 'Close'
            if isinstance(gold_df.columns, pd.MultiIndex):
                gold_series = gold_df[col].iloc[:, 0]
            else:
                gold_series = gold_df[col]
            latest_gold_price = float(gold_series.iloc[-1])
            print(f"Latest Gold Price: ₹{latest_gold_price:.2f}")
            
            gold_trend_filter = barbell_cfg.get('gold_trend_filter', False)
            gold_trend_lookback = barbell_cfg.get('gold_trend_lookback_days', 50)
            if gold_trend_filter:
                gold_ma = gold_series.rolling(window=gold_trend_lookback).mean()
                is_gold_bullish = latest_gold_price > gold_ma.iloc[-1]
                if is_gold_bullish:
                    print(f"✨ GOLD REGIME: BULLISH (Price ₹{latest_gold_price:.2f} > {gold_trend_lookback}DMA ₹{gold_ma.iloc[-1]:.2f})")
                else:
                    print(f"✨ GOLD REGIME: BEARISH (Price ₹{latest_gold_price:.2f} <= {gold_trend_lookback}DMA ₹{gold_ma.iloc[-1]:.2f})")
        except Exception as e:
            print(f"⚠️ Warning: Could not download gold price or calculate MA: {e}")
            latest_gold_price = float(input("Enter current price of GOLDBEES.NS (₹): ") or 70.0)

    # Determine market regime early based on configured regime_filter
    rebalance_freq = cap_cfg.get('rebalance_frequency', 'W-FRI')
    regime_filter = regime_cfg.get('regime_filter', '200dma')
    is_bull_market = True
    bench_prices = None
    
    if regime_filter and regime_filter != 'none':
        try:
            import re
            bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
            if 'dma' in str(regime_filter):
                match = re.search(r'\d+', str(regime_filter))
                window = int(match.group()) if match else 200
                bench_dma = bench_prices.rolling(window=window).mean()
                is_bull_market = bench_prices.iloc[-1] > bench_dma.iloc[-1]
            elif 'roc' in str(regime_filter):
                match = re.search(r'\d+', str(regime_filter))
                lookback = int(match.group()) if match else 60
                bench_roc = bench_prices.pct_change(periods=lookback)
                is_bull_market = bench_roc.iloc[-1] > 0
            elif 'breakout' in str(regime_filter):
                match = re.search(r'\d+', str(regime_filter))
                window = int(match.group()) if match else 50
                bench_highs = bench_prices.shift(1).rolling(window=window).max()
                bench_lows = bench_prices.shift(1).rolling(window=window).min()
                
                # Trace chronological state to find final is_bull_market
                state = True
                for d in bench_prices.index:
                    p = bench_prices.loc[d]
                    h = bench_highs.loc[d]
                    l = bench_lows.loc[d]
                    if pd.notna(p) and pd.notna(h) and pd.notna(l):
                        if p > h:
                            state = True
                        elif p < l:
                            state = False
                is_bull_market = state
        except Exception as e:
            print(f"⚠️ Warning: Could not calculate regime filter ({regime_filter}): {e}. Defaulting to Bull Market.")
            is_bull_market = True

    # Calculate ADX Trend Strength
    is_trending = True
    use_adx_filter = regime_cfg.get('use_adx_filter', False)
    adx_threshold = regime_cfg.get('adx_threshold', 20)
    adx_window = regime_cfg.get('adx_window', 14)
    
    if use_adx_filter:
        try:
            if bench_prices is None:
                bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
            
            diff = bench_prices.diff()
            plus_dm = diff.clip(lower=0)
            minus_dm = (-diff).clip(lower=0)
            tr = diff.abs()
            
            atr = tr.ewm(alpha=1.0/adx_window, adjust=False).mean()
            atr[atr == 0] = 0.00001
            
            plus_di = 100 * plus_dm.ewm(alpha=1.0/adx_window, adjust=False).mean() / atr
            minus_di = 100 * minus_dm.ewm(alpha=1.0/adx_window, adjust=False).mean() / atr
            plus_di = plus_di.fillna(0)
            minus_di = minus_di.fillna(0)
            
            denom = plus_di + minus_di
            denom[denom == 0] = 1.0
            dx = 100 * (plus_di - minus_di).abs() / denom
            dx = dx.fillna(0)
            bench_adx = dx.ewm(alpha=1.0/adx_window, adjust=False).mean()
            
            latest_adx = bench_adx.iloc[-1]
            is_trending = latest_adx >= adx_threshold
            print(f"📈 BENCHMARK ADX: {latest_adx:.2f} (Threshold: {adx_threshold} | Trending: {is_trending})")
        except Exception as e:
            print(f"⚠️ Warning: Could not calculate ADX filter: {e}. Defaulting to Trending.")
            is_trending = True

    if is_barbell:
        if regime_filter == 'none':
            print("⚪ MARKET REGIME FILTER: DISABLED (Always Bullish)")
        else:
            if is_bull_market:
                print(f"🟢 MARKET REGIME: BULLISH (Benchmark > {regime_filter})")
            else:
                print(f"🔴 MARKET REGIME: BEARISH (Benchmark < {regime_filter})")

    # --- DYNAMIC SIZING MATH ---
    print("\n--- Portfolio Valuation ---")
    stock_value = sum(current_positions[t] * latest_prices.get(t, 0) for t in current_positions if t != 'GOLDBEES.NS')
    gold_shares = current_positions.get('GOLDBEES.NS', 0)
    gold_value = gold_shares * latest_gold_price if is_barbell else 0.0
    pos_value = stock_value + gold_value
    
    print(f"Current Stock Positions Value: ₹{stock_value:,.2f}")
    if is_barbell:
        print(f"Current Gold Value:           ₹{gold_value:,.2f} ({gold_shares} shares)")
    print(f"Total Positions Value:        ₹{pos_value:,.2f}")
    
    try:
        user_cash_input = input("Enter your Current Portfolio Cash (₹) [or press Enter for default]: ").strip()
        user_cash = float(user_cash_input) if user_cash_input else (cap_cfg.get('allocation_per_slot', 25000) * (portfolio_size if not is_barbell else (portfolio_size * 2)))
    except ValueError:
        user_cash = cap_cfg.get('allocation_per_slot', 25000) * (portfolio_size if not is_barbell else (portfolio_size * 2))
        
    total_live_equity = pos_value + user_cash
    
    if is_barbell:
        safe_weight = safe_weight_bull if is_bull_market else safe_weight_bear
        target_safe_value = total_live_equity * safe_weight
        target_risk_value = total_live_equity * (1 - safe_weight)
        
        active_gold_ratio = gold_ratio_in_safe if is_gold_bullish else 0.0
        target_gold_value = target_safe_value * active_gold_ratio
        target_cash_value = target_safe_value * (1 - active_gold_ratio)
        
        allocation_per_slot = target_risk_value / portfolio_size
        target_gold_shares = math.floor(target_gold_value / latest_gold_price) if latest_gold_price > 0 else 0
        
        print(f"Total Portfolio Equity:  ₹{total_live_equity:,.2f}")
        print(f"Target Safe Assets:      ₹{target_safe_value:,.2f} ({safe_weight*100:.0f}%)")
        print(f"  - Target Gold Value:   ₹{target_gold_value:,.2f} ({target_gold_shares} shares - Active split: {active_gold_ratio*100:.0f}%)")
        print(f"  - Target Liquid Cash:  ₹{target_cash_value:,.2f}")
        print(f"Target Aggressive Slots: ₹{target_risk_value:,.2f} ({(1-safe_weight)*100:.0f}%)")
        print(f"Dynamic Budget per Slot: ₹{allocation_per_slot:,.2f} (Across {portfolio_size} slots)")
    else:
        allocation_per_slot = total_live_equity / portfolio_size
        print(f"Total Portfolio Equity:  ₹{total_live_equity:,.2f}")
        print(f"Dynamic Budget per Slot: ₹{allocation_per_slot:,.2f}")

    momentum_df = data_mgr.calculate_momentum(lookback_days=lookback_days)
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=lookback_days)

    # Logic for skipping latest period (Momentum Lag)
    if skip_latest_period:
        resampled_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
        if len(resampled_momentum) >= 2:
            latest_momentum = resampled_momentum.iloc[-2]
            print("ℹ️ Strategy: Using lagged momentum score (skipped latest week) for ranking.")
        else:
            latest_momentum = momentum_df.iloc[-1]
    else:
        latest_momentum = momentum_df.iloc[-1]

    latest_highs = rolling_highs_df.iloc[-1]
    
    # Filter out stocks too expensive for the current budget
    affordable_tickers = latest_prices[latest_prices <= allocation_per_slot].index
    latest_momentum = latest_momentum.reindex(affordable_tickers).dropna()
    
    if not is_barbell:
        if regime_filter == 'none':
            print("⚪ MARKET REGIME FILTER: DISABLED (Always Bullish)")
        else:
            if is_bull_market:
                print(f"🟢 MARKET REGIME: BULLISH (Benchmark > {regime_filter})")
            else:
                print(f"🔴 MARKET REGIME: BEARISH (Benchmark < {regime_filter})")
                print("⚠️ ACTION: Stop new entries. Park available cash in 100% Gold (GOLDBEES).")
        if use_adx_filter:
            if not is_trending:
                print(f"⚠️ ADX WARNING: Market is Sideways (ADX = {latest_adx:.2f} < {adx_threshold}). Blocking all new entries.")
            else:
                print(f"📈 ADX STATUS: Market is Trending (ADX = {latest_adx:.2f} >= {adx_threshold}). New entries allowed.")

    strategy = MomentumStrategy(
        portfolio_size=portfolio_size,
        entry_rank=entry_rank,
        exit_rank=exit_rank,
        drawdown_limit=drawdown_limit,
        verbose=False
    )
    
    # Target signals generation
    allow_new_entries = is_bull_market and is_trending
    
    if is_barbell:
        # Barbell ignores the regime filter (per grill-me alignment)
        target_portfolio = strategy.get_target_portfolio(latest_momentum,
                                                        current_tickers, 
                                                        latest_prices, 
                                                        latest_highs,
                                                        market_bullish=True)
    else:
        if not is_bull_market and regime_cfg.get('liquidate_on_bear_market', False):
            target_portfolio = []
        else:
            target_portfolio = strategy.get_target_portfolio(latest_momentum,
                                                            current_tickers, 
                                                            latest_prices, 
                                                            latest_highs,
                                                            market_bullish=allow_new_entries)
    
    # --- DISPLAY TOP LEADERS ---
    latest_price_date = prices.index[-1].strftime('%Y-%m-%d')
    print("\n" + "="*60)
    print(f"🏆 TOP {strategy.exit_rank} MOMENTUM LEADERS (Prices as of {latest_price_date})")
    print("="*60)
    print(f"{'Rank':<5} | {'Ticker':<15} | {'Score':<10} | {'Price':<10}")
    print("-" * 55)
    
    drawdown_mask = latest_prices > (latest_highs * (1 - strategy.drawdown_limit))
    qualified_momentum = latest_momentum[drawdown_mask].sort_values(ascending=False).head(strategy.exit_rank)
    
    for i, (ticker, score) in enumerate(qualified_momentum.items()):
        price = latest_prices.get(ticker, 0)
        print(f"{i+1:<5} | {ticker:<15} | {score:<10.2f} | ₹{price:<9.2f}")
    print("="*60)

    print("="*60)
    # Trackers for the current state and ledger
    new_positions = {}
    executed_trades = []
    
    sells = [t for t in current_tickers if t not in target_portfolio]
    buys = [t for t in target_portfolio if t not in current_tickers]
    holds = [t for t in current_tickers if t in target_portfolio]
    
    # Integrate Gold trades for Barbell
    gold_diff = 0
    if is_barbell:
        gold_diff = target_gold_shares - gold_shares
        if gold_diff > 0:
            buys.append('GOLDBEES.NS')
        elif gold_diff < 0:
            sells.append('GOLDBEES.NS')

    print("\n" + "="*50)
    print("               ACTION REQUIRED")
    print("="*50)
    
    # --- PROCESS SELLS ---
    if sells:
        print("\n🔴 SELL (Liquidate/Reduce):")
        for ticker in sells:
            if ticker == 'GOLDBEES.NS':
                shares_to_sell = abs(gold_diff)
                print(f"   -> GOLDBEES.NS: Sell {shares_to_sell} shares to rebalance Safe Leg (Last Price: ₹{latest_gold_price:.2f})")
                executed_trades.append({
                    'Date': run_date, 'Action': 'SELL', 'Ticker': 'GOLDBEES.NS',
                    'Shares': shares_to_sell, 'Execution_Price': round(latest_gold_price, 2),
                    'Total_Amount': round(shares_to_sell * latest_gold_price, 2)
                })
            else:
                shares = current_positions[ticker]
                price = latest_prices.get(ticker, 0)
                print(f"   -> {ticker}: Sell all {shares} shares (Last Price: ₹{price:.2f})")
                executed_trades.append({
                    'Date': run_date, 'Action': 'SELL', 'Ticker': ticker,
                    'Shares': shares, 'Execution_Price': round(price, 2),
                    'Total_Amount': round(shares * price, 2)
                })
    else:
        print("\n🔴 SELL: None")

    # --- PROCESS BUYS ---
    if buys:
        print(f"\n🟢 BUY:")
        for ticker in buys:
            if ticker == 'GOLDBEES.NS':
                shares_to_buy = gold_diff
                cost = shares_to_buy * latest_gold_price
                print(f"   -> GOLDBEES.NS: Buy {shares_to_buy} shares to rebalance Safe Leg @ ~₹{latest_gold_price:.2f} (Total: ₹{cost:,.2f})")
                executed_trades.append({
                    'Date': run_date, 'Action': 'BUY', 'Ticker': 'GOLDBEES.NS',
                    'Shares': shares_to_buy, 'Execution_Price': round(latest_gold_price, 2),
                    'Total_Amount': round(cost, 2)
                })
            else:
                price = latest_prices.get(ticker, 0)
                if pd.notna(price) and price > 0:
                    shares = math.floor(allocation_per_slot / price)
                    cost = shares * price
                    print(f"   -> {ticker}: Buy {shares} shares @ ~₹{price:.2f} (Total: ₹{cost:,.2f})")
                    new_positions[ticker] = shares
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
         
    if is_barbell and gold_shares > 0 and gold_diff == 0:
        print(f"   -> GOLDBEES.NS: {gold_shares} shares")
        
    print("="*50)
    
    # --- CONFIRMATION & LOGGING ---
    if buys or sells:
        print("\n" + "="*50)
        print("          CONFIRM ACTUAL EXECUTION")
        print("="*50)
        print("⚠️  Enter the ACTUAL values from your broker (or press Enter to accept suggestion)")
        
        final_executed_trades = []
        final_new_positions = {}
        
        # 1. Carry over Holds
        for ticker, shares in current_positions.items():
            if ticker in holds or (ticker == 'GOLDBEES.NS' and gold_diff == 0):
                final_new_positions[ticker] = shares

        # 2. Confirm Sells
        for ticker in sells:
            if ticker == 'GOLDBEES.NS':
                shares_suggested = abs(gold_diff)
                price_suggested = latest_gold_price
            else:
                shares_suggested = current_positions[ticker]
                price_suggested = latest_prices.get(ticker, 0)
            
            print(f"\n🔴 SELL {ticker}:")
            try:
                inp_shares = input(f"   Actual Shares Sold [{shares_suggested}]: ").strip()
                shares_actual = int(inp_shares) if inp_shares else shares_suggested
                
                inp_price = input(f"   Actual Fill Price [₹{price_suggested:.2f}]: ").strip()
                price_actual = float(inp_price) if inp_price else price_suggested
            except ValueError:
                print("   ❌ Invalid input. Skipping record update for this ticker.")
                continue

            final_executed_trades.append({
                'Date': run_date, 'Action': 'SELL', 'Ticker': ticker,
                'Shares': shares_actual, 'Execution_Price': round(price_actual, 2),
                'Total_Amount': round(shares_actual * price_actual, 2)
            })
            
            if ticker == 'GOLDBEES.NS':
                new_gold = gold_shares - shares_actual
                if new_gold > 0:
                    final_new_positions['GOLDBEES.NS'] = new_gold

        # 3. Confirm Buys
        for ticker in buys:
            if ticker == 'GOLDBEES.NS':
                shares_suggested = gold_diff
                price_suggested = latest_gold_price
            else:
                price_suggested = latest_prices.get(ticker, 0)
                shares_suggested = math.floor(allocation_per_slot / price_suggested) if price_suggested > 0 else 0
            
            print(f"\n🟢 BUY {ticker}:")
            try:
                inp_shares = input(f"   Actual Shares Bought [{shares_suggested}]: ").strip()
                shares_actual = int(inp_shares) if inp_shares else shares_suggested
                
                inp_price = input(f"   Actual Fill Price [₹{price_suggested:.2f}]: ").strip()
                price_actual = float(inp_price) if inp_price else price_suggested
            except ValueError:
                print("   ❌ Invalid input. Skipping record update for this ticker.")
                continue

            if shares_actual > 0:
                final_executed_trades.append({
                    'Date': run_date, 'Action': 'BUY', 'Ticker': ticker,
                    'Shares': shares_actual, 'Execution_Price': round(price_actual, 2),
                    'Total_Amount': round(shares_actual * price_actual, 2)
                })
                if ticker == 'GOLDBEES.NS':
                    final_new_positions['GOLDBEES.NS'] = gold_shares + shares_actual
                else:
                    final_new_positions[ticker] = shares_actual

        print("\n" + "-"*50)
        confirmation = input("Update files with these ACTUAL values? (y/n): ").strip().lower()
        
        if confirmation == 'y':
            save_new_positions(final_new_positions, holdings_file)
            append_to_journal(final_executed_trades, journal_file)
        else:
            print("\n❌ CANCELED: Logs were NOT updated.")
    else:
        print("\n✅ No trades required today.")

if __name__ == "__main__":
    generate_weekly_signals(force_refresh=False)