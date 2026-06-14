import os
import re
import json
import math
import bisect
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from tqdm import tqdm
from datetime import datetime

# Import shared analytics
from analytics import calculate_metrics, convert_journal_to_ledger, TradeAnalyzer

def load_config(config_path='config_basso.json'):
    with open(config_path, 'r') as f:
        return json.load(f)

def download_ohlcv_cache(config):
    paths = config['paths']
    bt_cfg = config['backtest']
    cache_path = paths['cache_file']
    
    if os.path.exists(cache_path):
        print(f"[DATA] Loading cached daily OHLCV data from {cache_path}...")
        return pd.read_parquet(cache_path)
        
    print("[DATA] Cache file not found. Initializing Yahoo Finance bulk download...")
    symbols_df = pd.read_csv(paths['symbols_file'])
    tickers = [f"{sym.strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    benchmark = config['strategy']['benchmark_ticker']
    if benchmark not in tickers:
        tickers.append(benchmark)
        
    start_date = bt_cfg['start_date']
    end_date = bt_cfg['end_date']
    
    print(f"[DATA] Downloading {len(tickers)} tickers from {start_date} to {end_date}...")
    
    # Bulk download is significantly faster than single downloads
    df = yf.download(tickers, start=start_date, end=end_date, auto_adjust=True)
    
    # Check for completely missing tickers
    failed_tickers = []
    for t in tickers:
        if ('Close', t) not in df.columns or df['Close'][t].isna().all():
            failed_tickers.append(t)
            
    if failed_tickers:
        print(f"[DATA] Retrying {len(failed_tickers)} failed tickers individually...")
        for t in tqdm(failed_tickers, desc="Retrying Tickers"):
            try:
                temp = yf.download(t, start=start_date, end=end_date, auto_adjust=True, progress=False)
                if not temp.empty:
                    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                        if col in temp.columns:
                            # Assign directly to avoid multi-index insertion issues
                            df.loc[temp.index, (col, t)] = temp[col]
            except Exception as e:
                print(f"[WARN] Retry failed for {t}: {e}")
                
    # Save cache
    df.to_parquet(cache_path)
    print(f"[OK] Download complete. Saved to {cache_path}")
    return df



def run_backtest_simulation():
    print("====================================================")
    config = load_config()
    strat_cfg = config['strategy']
    paths = config['paths']
    bt_cfg = config['backtest']
    initial_capital = bt_cfg.get('initial_capital', 10000000)
    cash_yield = strat_cfg.get('cash_yield', 0.0)
    risk_pct_bull = strat_cfg.get('risk_pct_bull', 0.01)
    risk_pct_bear = strat_cfg.get('risk_pct_bear', 0.0)
    use_regime_filter = strat_cfg.get('use_regime_filter', True)
    relative_strength_lookback = strat_cfg.get('relative_strength_lookback', 0)
    relative_strength_min_return = strat_cfg.get('relative_strength_min_return', 0.0)
    entry_sma_window = strat_cfg.get('entry_sma_window', 21)
    exit_sma_window = strat_cfg.get('exit_sma_window', 21)
    candidate_ranking_method = strat_cfg.get('candidate_ranking_method', 'turnover')
    use_keltner_channel = strat_cfg.get('use_keltner_channel', False)
    keltner_ema_window = strat_cfg.get('keltner_ema_window', 20)
    keltner_multiplier = strat_cfg.get('keltner_multiplier', 2.0)
    transaction_cost_pct = 0.0001 # 0.01% friction
    
    df = download_ohlcv_cache(config)
    
    # Identify universe (exclude benchmark index)
    tickers = [t for t in df['Close'].columns if t != strat_cfg['benchmark_ticker']]
    
    # 2. Extract price fields
    opens = df['Open']
    highs = df['High']
    lows = df['Low']
    closes = df['Close']
    volumes = df['Volume']
    
    # 3. Precompute Indicator matrices for performance
    print("[INFO] Precomputing indicators (Turnover, ATR, SMA)...")
    
    # Benchmark Regime (200 SMA of Nifty 50 index)
    bench_ticker = strat_cfg['benchmark_ticker']
    bench_closes = closes[bench_ticker].ffill()
    bench_sma = bench_closes.rolling(window=strat_cfg['regime_sma_window']).mean()
    bench_regime = bench_closes > bench_sma  # True = Bullish, False = Bearish
    
    # Turnover (Volume * Close) and 20-day Average Turnover
    turnover = volumes * closes
    avg_turnover = turnover.rolling(window=strat_cfg['turnover_window']).mean()
    liquidity_mask = avg_turnover > strat_cfg['turnover_threshold']
    
    # Volatility (20-day Average True Range)
    prev_closes = closes.shift(1)
    tr_dict = {}
    for t in tickers:
        h = highs[t]
        l = lows[t]
        pc = prev_closes[t]
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        tr_dict[t] = tr
    
    tr_df = pd.DataFrame(tr_dict, index=closes.index)
    atr_df = tr_df.rolling(window=strat_cfg['atr_window']).mean()
    
    # 3. Precompute SMAs / Keltner Bands
    if use_keltner_channel:
        print(f"[INFO] Precomputing Keltner Channels (EMA {keltner_ema_window}, Mult {keltner_multiplier})...")
        ema_mid = closes.ewm(span=keltner_ema_window, adjust=False).mean()
        keltner_upper = ema_mid + (keltner_multiplier * atr_df)
        entry_barrier = keltner_upper
        exit_barrier = ema_mid
    else:
        print("[INFO] Precomputing SMAs...")
        sma_entry = closes.rolling(window=entry_sma_window).mean()
        sma_exit = closes.rolling(window=exit_sma_window).mean()
        entry_barrier = sma_entry
        exit_barrier = sma_exit

    # 4. Simulation Variables
    dates = closes.index
    cash = initial_capital
    positions = {}  # {ticker: {'shares': int, 'stop_loss': float, 'entry_price': float, 'entry_date': Timestamp}}
    
    daily_equity_history = []
    trade_journal = []
    
    # Find starting index based on configured start_date (with at least 200 days history for SMA warm-up)
    start_dt = pd.to_datetime(bt_cfg.get('start_date', '2016-01-01'))
    start_idx = closes.index.get_indexer([start_dt], method='bfill')[0]
    if start_idx < 0:
        start_idx = len(dates) - 1
    min_idx = 200
    while min_idx < len(dates) and pd.isna(bench_sma.iloc[min_idx]):
        min_idx += 1
    start_idx = max(start_idx, min_idx)
        
    print(f"[RUN] Running daily simulation loop from {dates[start_idx].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}...")
    
    def get_safe_close(ticker, index):
        p = closes[ticker].iloc[index]
        if pd.isna(p):
            p = closes[ticker].iloc[:index].ffill().iloc[-1]
        return p

    for idx in range(start_idx, len(dates)):
        date = dates[idx]
        prev_date = dates[idx - 1]
        
        # Add cash yield on uninvested cash
        if cash_yield > 0:
            days_passed = (date - prev_date).days
            if days_passed > 0:
                interest = cash * cash_yield * (days_passed / 365.0)
                cash += interest
        
        # 4a. Update Valuation (using today's Close prices)
        # Note: If ticker is currently not traded/NaN today, forward fill close valuation
        pos_val = sum(pos_info['shares'] * get_safe_close(t, idx) for t, pos_info in positions.items())
            
        current_equity = cash + pos_val
        
        # 4b. Check Exit Triggers (breached on previous day close `idx-1`)
        # The crossover exit happens on the previous day close.
        # Triggered positions are liquidated at index `idx` open (today's Open).
        exits_to_execute = []
        for t, pos_info in positions.items():
            # Check if Close on previous day crossed below exit barrier
            prev_close = closes[t].iloc[idx - 1]
            prev_exit_barrier = exit_barrier[t].iloc[idx - 1]
            if pd.notna(prev_close) and pd.notna(prev_exit_barrier) and prev_close < prev_exit_barrier:
                exits_to_execute.append(t)
                
        # Execute Exits
        for t in exits_to_execute:
            pos_info = positions.pop(t)
            open_price = opens[t].iloc[idx]
            if pd.isna(open_price):
                # Fallback to previous close if open is missing
                open_price = closes[t].iloc[:idx].ffill().iloc[-1]
                
            shares = pos_info['shares']
            gross_value = shares * open_price
            commission = gross_value * transaction_cost_pct
            net_proceeds = gross_value - commission
            
            cash += net_proceeds
            pnl_pct = (open_price - pos_info['entry_price']) / pos_info['entry_price']
            days_held = (date - pos_info['entry_date']).days
            
            trade_journal.append({
                'Date': date.strftime('%Y-%m-%d'),
                'Action': 'SELL',
                'Ticker': t,
                'Shares': shares,
                'Price': round(open_price, 2),
                'Total Value': round(net_proceeds, 2),
                'Entry Date': pos_info['entry_date'].strftime('%Y-%m-%d'),
                'Entry Price': round(pos_info['entry_price'], 2),
                'PnL %': round(pnl_pct * 100, 2),
                'Days Held': days_held
            })
            
        # Re-value equity post-exits (valuation at today's close remains correct)
        pos_val = sum(pos_info['shares'] * get_safe_close(t, idx) for t, pos_info in positions.items())
        current_equity = cash + pos_val
        
        # 4c. Check Entry Signals (triggered on previous day close `idx-1` / day d-1)
        buy_candidates = []
        
        for t in tickers:
            if t in positions:
                continue  # Already hold this stock
                
            # Liquidity Check (Turnover > 15 Cr)
            if not liquidity_mask[t].iloc[idx - 1]:
                continue
            # Crossover Entry
            barrier_val = entry_barrier[t].iloc[idx - 1]
            barrier_val_prev = entry_barrier[t].iloc[idx - 2]
            close_prev = closes[t].iloc[idx - 1]
            close_prev_prev = closes[t].iloc[idx - 2]
            
            if pd.notna(barrier_val) and pd.notna(barrier_val_prev):
                is_crossover = (close_prev > barrier_val) and (close_prev_prev <= barrier_val_prev)
                if is_crossover:
                    # Relative Strength Filter (e.g. 60-day return > 10%)
                    if relative_strength_lookback > 0:
                        if idx - 1 - relative_strength_lookback < 0:
                            continue
                        close_lookback = closes[t].iloc[idx - 1 - relative_strength_lookback]
                        if pd.isna(close_lookback) or close_lookback <= 0:
                            continue
                        roc = (close_prev - close_lookback) / close_lookback
                        if roc <= relative_strength_min_return:
                            continue
                    buy_candidates.append(t)
                        
        # 4d. Execute Buy Candidates (at index `idx` open)
        if buy_candidates:
            if candidate_ranking_method == 'momentum':
                # Rank by 60d return on day d-1
                def get_momentum(ticker):
                    close_prev = closes[ticker].iloc[idx - 1]
                    close_lookback = closes[ticker].iloc[idx - 1 - relative_strength_lookback]
                    if pd.isna(close_prev) or pd.isna(close_lookback) or close_lookback <= 0:
                        return -999.0
                    return (close_prev - close_lookback) / close_lookback
                buy_candidates = sorted(buy_candidates, key=get_momentum, reverse=True)
            else:
                buy_candidates = sorted(buy_candidates, key=lambda x: avg_turnover[x].iloc[idx - 1], reverse=True)
            
            for t in buy_candidates:
                atr = atr_df[t].iloc[idx - 1]
                if pd.isna(atr) or atr <= 0:
                    continue
                    
                # Sizing: Dynamic Regime risk allocation / 20-day ATR
                if use_regime_filter:
                    is_bull = bench_regime.iloc[idx - 1]
                    active_risk = risk_pct_bull if is_bull else risk_pct_bear
                else:
                    active_risk = risk_pct_bull
                target_qty = math.floor((current_equity * active_risk) / atr)
                
                # Check cash constraint
                open_price = opens[t].iloc[idx]
                if pd.isna(open_price) or open_price <= 0:
                    continue
                    
                max_affordable = math.floor(cash / (open_price * (1 + transaction_cost_pct)))
                shares_to_buy = min(target_qty, max_affordable)
                
                if shares_to_buy > 0:
                    gross_cost = shares_to_buy * open_price
                    commission = gross_cost * transaction_cost_pct
                    total_cost = gross_cost + commission
                    
                    cash -= total_cost
                    
                    # Initial stop loss: set to the exit barrier at day idx-1
                    initial_sl = exit_barrier[t].iloc[idx - 1]
                    if pd.isna(initial_sl) or initial_sl <= 0 or initial_sl >= open_price:
                        initial_sl = open_price - (3 * atr)
                        
                    positions[t] = {
                        'shares': shares_to_buy,
                        'stop_loss': initial_sl,
                        'entry_price': open_price,
                        'entry_date': date
                    }
                    
                    trade_journal.append({
                        'Date': date.strftime('%Y-%m-%d'),
                        'Action': 'BUY',
                        'Ticker': t,
                        'Shares': shares_to_buy,
                        'Price': round(open_price, 2),
                        'Total Value': round(total_cost, 2),
                        'Entry Date': date.strftime('%Y-%m-%d'),
                        'Entry Price': round(open_price, 2),
                        'PnL %': 0.0,
                        'Days Held': 0
                    })
                    
        # 4e. Trailing Stop Loss Update (at index `idx` close)
        # Update trailing stop to the current exit barrier (if it moves up)
        for t, pos_info in positions.items():
            sl1 = exit_barrier[t].iloc[idx]
            if pd.notna(sl1) and sl1 > pos_info['stop_loss']:
                pos_info['stop_loss'] = sl1
                
        # 4f. Record Daily Snapshot (valuation post trades)
        pos_val = sum(pos_info['shares'] * get_safe_close(t, idx) for t, pos_info in positions.items())
        current_equity = cash + pos_val
        
        daily_equity_history.append({
            'Date': date,
            'Total Equity': current_equity,
            'Cash': cash,
            'Invested Value': pos_val,
            'Active Positions': len(positions),
            'Holdings': ", ".join([f"{t}: {pos['shares']}" for t, pos in positions.items()]) if positions else "Cash"
        })
        
    # 5. Save Backtest Output
    results_df = pd.DataFrame(daily_equity_history)
    results_df.set_index('Date', inplace=True)
    results_df.to_csv(paths['results_file'])
    
    journal_df = pd.DataFrame(trade_journal)
    journal_df.to_csv(paths['journal_file'], index=False)
    
    print(f"[OK] Simulation finished. Results saved to {paths['results_file']}")
    print(f"[OK] Trade journal saved to {paths['journal_file']}")
    
    # 6. Generate tearsheet summary
    calculate_and_save_summary(results_df, journal_df, config, closes[bench_ticker])

def calculate_and_save_summary(results_df, journal_df, config, bench_series):
    paths = config['paths']
    bt_cfg = config['backtest']
    
    start_date = results_df.index[0].strftime('%Y-%m-%d')
    end_date = results_df.index[-1].strftime('%Y-%m-%d')
    initial_capital = bt_cfg['initial_capital']
    
    # Metrics
    sliced_bench = bench_series.loc[results_df.index[0]:results_df.index[-1]]
    metrics = calculate_metrics(results_df['Total Equity'], initial_capital, start_date, end_date, sliced_bench)
    
    # Benchmark calculations
    years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
    bench_start = sliced_bench.iloc[0]
    bench_end = sliced_bench.iloc[-1]
    bench_abs_return = ((bench_end - bench_start) / bench_start) * 100
    bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    rolling_max_bench = sliced_bench.cummax()
    drawdown_bench = (sliced_bench - rolling_max_bench) / rolling_max_bench
    max_dd_bench = drawdown_bench.min() * 100
    
    # Trade analytics
    # Create clean universal trade ledger
    closed_trades = journal_df[journal_df['Action'] == 'SELL']
    total_trades = len(closed_trades)
    
    win_rate = "N/A"
    profit_factor = "N/A"
    payoff_ratio = "N/A"
    win_loss = "N/A"
    avg_days_held = "N/A"
    
    if not closed_trades.empty:
        # Convert journal to ledger format compatible with TradeAnalyzer
        ledger_trades = []
        for _, row in closed_trades.iterrows():
            ledger_trades.append({
                'Ticker': row['Ticker'],
                'Entry_Date': pd.to_datetime(row['Entry Date']),
                'Entry_Price': float(row['Entry Price']),
                'Exit_Date': pd.to_datetime(row['Date']),
                'Exit_Price': float(row['Price']),
                'PnL_Pct': float(row['PnL %']) / 100.0,
                'Days_Held': int(row['Days Held'])
            })
        ledger_df = pd.DataFrame(ledger_trades)
        analyzer = TradeAnalyzer(ledger_df)
        rep = analyzer.generate_report()
        
        win_rate = f"{rep['Win_Rate_Pct']}%"
        profit_factor = f"{rep['Profit_Factor']}"
        payoff_ratio = f"{rep['Payoff_Ratio']}"
        win_loss = f"+{rep['Average_Win_Pct']}% / -{rep['Average_Loss_Pct']}%"
        avg_days_held = f"{rep['Average_Days_Held']} days"
        
    summary_content = f"""# Tom Basso Breakout Strategy Backtest Report

## Run Details
* **Execution Date**: {datetime.now().strftime('%Y-%m-%d')}
* **Period**: {start_date} to {end_date}
* **Initial Capital**: INR {initial_capital:,.2f}
* **Final Equity**: INR {results_df['Total Equity'].iloc[-1]:,.2f}

## Performance Metrics
| Metric | Tom Basso Strategy | Benchmark (Nifty 50) |
| :--- | :--- | :--- |
| **Absolute Return** | {metrics.get('Abs Return %', 0.0):.2f}% | {bench_abs_return:.2f}% |
| **CAGR** | {metrics.get('CAGR %', 0.0):.2f}% | {bench_cagr:.2f}% |
| **Max Drawdown** | {metrics.get('Max DD %', 0.0):.2f}% | {max_dd_bench:.2f}% |
| **Alpha (CAGR Diff)** | {metrics.get('Alpha %', 0.0):+.2f}% | - |
| **Ret / DD Ratio** | {metrics.get('Ret/DD Ratio', 0.0):.2f} | {abs(bench_cagr / max_dd_bench):.2f} |
| **Total Trades (Closed)**| {total_trades} | - |

## Trade Analytics
* **Win Rate**: {win_rate}
* **Profit Factor**: {profit_factor}
* **Payoff Ratio**: {payoff_ratio}
* **Average Win / Loss**: {win_loss}
* **Average Days Held**: {avg_days_held}
"""
    
    with open(paths['summary_file'], 'w', encoding='utf-8') as f:
        f.write(summary_content)
        
    print(f"[OK] Tearsheet markdown written to {paths['summary_file']}")
    print("\n" + "="*80)
    print("                      BACKTEST TEARSHEET SUMMARY")
    print("="*80)
    print(f"Absolute Return:       {metrics.get('Abs Return %', 0.0):.2f}% (Bench: {bench_abs_return:.2f}%)")
    print(f"CAGR:                  {metrics.get('CAGR %', 0.0):.2f}% (Bench: {bench_cagr:.2f}%)")
    print(f"Max Drawdown:          {metrics.get('Max DD %', 0.0):.2f}% (Bench: {max_dd_bench:.2f}%)")
    print(f"Total Trades:          {total_trades}")
    print(f"Win Rate:              {win_rate}")
    print(f"Profit Factor:         {profit_factor}")
    print(f"Average Days Held:     {avg_days_held}")
    print("="*80 + "\n")
    
    # 7. Plot Performance
    plot_results(results_df, sliced_bench)

def plot_results(results_df, bench_series):
    plt.style.use('seaborn-v0_8-darkgrid')
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                   gridspec_kw={'height_ratios': [3, 1]}, 
                                   sharex=True)
    
    # Top Chart: Equity Growth normalized to initial index
    strategy_curve = results_df['Total Equity']
    initial_cap = strategy_curve.iloc[0]
    
    bench_normalized = (bench_series / bench_series.iloc[0]) * initial_cap
    
    ax1.plot(strategy_curve.index, strategy_curve, label='Tom Basso Breakout Strategy', color='#636EFA', linewidth=2)
    ax1.plot(bench_normalized.index, bench_normalized, label='Nifty 50 Benchmark', color='#EF553B', linewidth=1.5, linestyle='--')
    
    ax1.set_title('Tom Basso Breakout Strategy vs Nifty 50', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Portfolio Value (INR)', fontsize=12)
    ax1.yaxis.set_major_formatter(plt.matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
    ax1.legend(loc='upper left')
    
    # Bottom Chart: Cash vs Active Positions Count
    ax2.plot(results_df.index, results_df['Active Positions'], label='Active Positions Count', color='#00CC96', linewidth=1.5)
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Active Positions', fontsize=12)
    ax2.legend(loc='upper left')
    
    plt.tight_layout()
    # Save the plot
    plot_file = 'basso_backtest_chart.png'
    plt.savefig(plot_file, dpi=300)
    print(f"[OK] Plot saved to {plot_file}")
    plt.close()

if __name__ == "__main__":
    run_backtest_simulation()
