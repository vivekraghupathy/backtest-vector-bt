import os
import json
import math
import pandas as pd
import numpy as np
from tqdm import tqdm
from analytics import calculate_metrics, TradeAnalyzer

def load_config(config_path='config_basso.json'):
    with open(config_path, 'r') as f:
        return json.load(f)

def run_simulation(entry_sma_window, exit_sma_window, ranking_method, df, config, avg_turnover_dict, atr_dict, liquidity_mask_dict, bench_regime_arr):
    strat_cfg = config['strategy']
    bt_cfg = config['backtest']
    initial_capital = bt_cfg.get('initial_capital', 10000000)
    cash_yield = strat_cfg.get('cash_yield', 0.0)
    risk_pct_bull = strat_cfg.get('risk_pct_bull', 0.01)
    risk_pct_bear = strat_cfg.get('risk_pct_bear', 0.0)
    use_regime_filter = strat_cfg.get('use_regime_filter', True)
    relative_strength_lookback = strat_cfg.get('relative_strength_lookback', 0)
    relative_strength_min_return = strat_cfg.get('relative_strength_min_return', 0.0)
    transaction_cost_pct = 0.0001 # 0.01% friction
    
    tickers = [t for t in df['Close'].columns if t != strat_cfg['benchmark_ticker']]
    
    opens = df['Open']
    closes = df['Close']
    closes_ffilled = closes.ffill()
    
    opens_dict = {t: opens[t].values for t in tickers}
    closes_dict = {t: closes[t].values for t in tickers}
    closes_ffilled_dict = {t: closes_ffilled[t].values for t in tickers}
    
    use_keltner_channel = strat_cfg.get('use_keltner_channel', False)
    keltner_multiplier = strat_cfg.get('keltner_multiplier', 2.0)
    
    if use_keltner_channel:
        atr_df = pd.DataFrame({t: atr_dict[t] for t in tickers}, index=closes.index)
        ema_entry = closes.ewm(span=entry_sma_window, adjust=False).mean()
        ema_exit = closes.ewm(span=exit_sma_window, adjust=False).mean()
        entry_barrier = ema_entry + keltner_multiplier * atr_df
        exit_barrier = ema_exit
    else:
        entry_barrier = closes.rolling(window=entry_sma_window).mean()
        exit_barrier = closes.rolling(window=exit_sma_window).mean()
        
    entry_barrier_dict = {t: entry_barrier[t].values for t in tickers}
    exit_barrier_dict = {t: exit_barrier[t].values for t in tickers}

    dates = closes.index
    cash = initial_capital
    positions = {}
    
    daily_equity_history = []
    trade_journal = []
    
    bt_cfg = config['backtest']
    start_dt = pd.to_datetime(bt_cfg.get('start_date', '2024-03-31'))
    start_idx = closes.index.get_indexer([start_dt], method='bfill')[0]
    if start_idx < 0:
        start_idx = len(dates) - 1
    min_idx = max(entry_sma_window, exit_sma_window) + 10
    start_idx = max(start_idx, min_idx)
        
    def get_safe_close(ticker, index):
        p = closes_ffilled_dict[ticker][index]
        return p

    for idx in range(start_idx, len(dates)):
        date = dates[idx]
        prev_date = dates[idx - 1]
        
        if cash_yield > 0:
            days_passed = (date - prev_date).days
            if days_passed > 0:
                interest = cash * cash_yield * (days_passed / 365.0)
                cash += interest
        
        pos_val = 0.0
        for t, pos_info in positions.items():
            p_val = get_safe_close(t, idx)
            if not np.isnan(p_val):
                pos_val += pos_info['shares'] * p_val
                
        current_equity = cash + pos_val
        
        exits_to_execute = []
        for t, pos_info in positions.items():
            prev_close = closes_dict[t][idx - 1]
            prev_exit_barrier = exit_barrier_dict[t][idx - 1]
            if not np.isnan(prev_close) and not np.isnan(prev_exit_barrier) and prev_close < prev_exit_barrier:
                exits_to_execute.append(t)
                
        for t in exits_to_execute:
            pos_info = positions.pop(t)
            open_price = opens_dict[t][idx]
            if np.isnan(open_price):
                open_price = get_safe_close(t, idx - 1)
                
            shares = pos_info['shares']
            gross_value = shares * open_price
            commission = gross_value * transaction_cost_pct
            net_proceeds = gross_value - commission
            
            cash += net_proceeds
            pnl_pct = (open_price - pos_info['entry_price']) / pos_info['entry_price']
            days_held = (date - pos_info['entry_date']).days
            
            trade_journal.append({
                'Ticker': t,
                'Entry_Date': pos_info['entry_date'],
                'Entry_Price': pos_info['entry_price'],
                'Exit_Date': date,
                'Exit_Price': open_price,
                'PnL_Pct': pnl_pct,
                'Days_Held': days_held
            })
            
        pos_val = 0.0
        for t, pos_info in positions.items():
            p_val = get_safe_close(t, idx)
            if not np.isnan(p_val):
                pos_val += pos_info['shares'] * p_val
        current_equity = cash + pos_val
        
        buy_candidates = []
        for t in tickers:
            if t in positions:
                continue
                
            if not liquidity_mask_dict[t][idx - 1]:
                continue
                
            barrier_val = entry_barrier_dict[t][idx - 1]
            barrier_val_prev = entry_barrier_dict[t][idx - 2]
            close_prev = closes_dict[t][idx - 1]
            close_prev_prev = closes_dict[t][idx - 2]
            
            if not np.isnan(barrier_val) and not np.isnan(barrier_val_prev):
                is_crossover = (close_prev > barrier_val) and (close_prev_prev <= barrier_val_prev)
                if is_crossover:
                    if relative_strength_lookback > 0:
                        if idx - 1 - relative_strength_lookback < 0:
                            continue
                        close_lookback = closes_dict[t][idx - 1 - relative_strength_lookback]
                        if np.isnan(close_lookback) or close_lookback <= 0:
                            continue
                        roc = (close_prev - close_lookback) / close_lookback
                        if roc <= relative_strength_min_return:
                            continue
                    buy_candidates.append(t)
                        
        if buy_candidates:
            if ranking_method == 'momentum':
                def get_momentum(ticker):
                    close_prev = closes_dict[ticker][idx - 1]
                    close_lookback = closes_dict[ticker][idx - 1 - relative_strength_lookback]
                    if np.isnan(close_prev) or np.isnan(close_lookback) or close_lookback <= 0:
                        return -999.0
                    return (close_prev - close_lookback) / close_lookback
                buy_candidates = sorted(buy_candidates, key=get_momentum, reverse=True)
            else:
                buy_candidates = sorted(buy_candidates, key=lambda x: avg_turnover_dict[x][idx - 1], reverse=True)
            
            for t in buy_candidates:
                atr = atr_dict[t][idx - 1]
                if np.isnan(atr) or atr <= 0:
                    continue
                    
                if use_regime_filter:
                    is_bull = bench_regime_arr[idx - 1]
                    active_risk = risk_pct_bull if is_bull else risk_pct_bear
                else:
                    active_risk = risk_pct_bull
                
                if active_risk <= 0:
                    continue
                    
                target_qty = math.floor((current_equity * active_risk) / atr)
                
                open_price = opens_dict[t][idx]
                if np.isnan(open_price) or open_price <= 0:
                    continue
                    
                max_affordable = math.floor(cash / (open_price * (1 + transaction_cost_pct)))
                shares_to_buy = min(target_qty, max_affordable)
                
                if shares_to_buy > 0:
                    gross_cost = shares_to_buy * open_price
                    commission = gross_cost * transaction_cost_pct
                    total_cost = gross_cost + commission
                    
                    cash -= total_cost
                    
                    initial_sl = exit_barrier_dict[t][idx - 1]
                    if np.isnan(initial_sl) or initial_sl <= 0 or initial_sl >= open_price:
                        initial_sl = open_price - (3 * atr)
                        
                    positions[t] = {
                        'shares': shares_to_buy,
                        'stop_loss': initial_sl,
                        'entry_price': open_price,
                        'entry_date': date
                    }
                    
        for t, pos_info in positions.items():
            sl1 = exit_barrier_dict[t][idx]
            if not np.isnan(sl1) and sl1 > pos_info['stop_loss']:
                pos_info['stop_loss'] = sl1
                
        pos_val = 0.0
        for t, pos_info in positions.items():
            p_val = get_safe_close(t, idx)
            if not np.isnan(p_val):
                pos_val += pos_info['shares'] * p_val
        current_equity = cash + pos_val
        daily_equity_history.append(current_equity)
        
    equity_curve = pd.Series(daily_equity_history, index=dates[start_idx:])
    
    bench_ticker = strat_cfg['benchmark_ticker']
    bench_closes = df['Close'][bench_ticker].ffill()
    sliced_bench = bench_closes.loc[equity_curve.index[0]:equity_curve.index[-1]]
    
    metrics = calculate_metrics(equity_curve, initial_capital, equity_curve.index[0], equity_curve.index[-1], sliced_bench)
    
    total_trades = len(trade_journal)
    win_rate = 0.0
    profit_factor = 0.0
    payoff_ratio = 0.0
    avg_days_held = 0.0
    
    if total_trades > 0:
        trades_df = pd.DataFrame(trade_journal)
        trades_df['Entry_Date'] = pd.to_datetime(trades_df['Entry_Date'])
        trades_df['Exit_Date'] = pd.to_datetime(trades_df['Exit_Date'])
        trades_df['PnL_Pct'] = trades_df['PnL_Pct'].astype(float)
        trades_df['Days_Held'] = trades_df['Days_Held'].astype(int)
        
        analyzer = TradeAnalyzer(trades_df)
        rep = analyzer.generate_report()
        if "Error" not in rep:
            win_rate = rep['Win_Rate_Pct']
            profit_factor = rep['Profit_Factor']
            payoff_ratio = rep['Payoff_Ratio']
            avg_days_held = rep['Average_Days_Held']
            
    return {
        'entry_sma': entry_sma_window,
        'exit_sma': exit_sma_window,
        'ranking_method': ranking_method,
        'abs_return': metrics.get('Abs Return %', 0.0),
        'cagr': metrics.get('CAGR %', 0.0),
        'max_dd': metrics.get('Max DD %', 0.0),
        'ret_dd_ratio': metrics.get('Ret/DD Ratio', 0.0),
        'trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'payoff_ratio': payoff_ratio,
        'avg_days': avg_days_held
    }

def main():
    print("[OPT] Loading configuration and parquet cache...", flush=True)
    config = load_config()
    cache_path = config['paths']['cache_file']
    df = pd.read_parquet(cache_path)
    
    strat_cfg = config['strategy']
    closes = df['Close']
    highs = df['High']
    lows = df['Low']
    volumes = df['Volume']
    
    print("[OPT] Precomputing shared indicators (Turnover, ATR, Benchmark SMA) once...", flush=True)
    
    bench_ticker = strat_cfg['benchmark_ticker']
    bench_closes = closes[bench_ticker].ffill()
    bench_sma = bench_closes.rolling(window=strat_cfg['regime_sma_window']).mean()
    bench_regime = bench_closes > bench_sma
    bench_regime_arr = bench_regime.values
    
    turnover = volumes * closes
    avg_turnover = turnover.rolling(window=strat_cfg['turnover_window']).mean()
    liquidity_mask = avg_turnover > strat_cfg['turnover_threshold']
    
    prev_closes = closes.shift(1)
    tr_dict = {}
    tickers = [t for t in df['Close'].columns if t != strat_cfg['benchmark_ticker']]
    for t in tqdm(tickers, desc="Calculating ATR"):
        h = highs[t]
        l = lows[t]
        pc = prev_closes[t]
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        tr_dict[t] = tr
    
    tr_df = pd.DataFrame(tr_dict, index=closes.index)
    atr_df = tr_df.rolling(window=strat_cfg['atr_window']).mean()
    
    avg_turnover_dict = {t: avg_turnover[t].values for t in tickers}
    atr_dict = {t: atr_df[t].values for t in tickers}
    liquidity_mask_dict = {t: liquidity_mask[t].values for t in tickers}
    
    entry_smas = [10, 15, 21, 30]
    exit_smas = [10, 15, 21]
    ranking_methods = ['turnover', 'momentum']
    
    results = []
    total_runs = len(entry_smas) * len(exit_smas) * len(ranking_methods)
    print(f"[OPT] Starting Parameter Sweep across {total_runs} combinations...", flush=True)
    
    run_count = 0
    for entry in entry_smas:
        for exit_s in exit_smas:
            for rank_m in ranking_methods:
                run_count += 1
                try:
                    res = run_simulation(entry, exit_s, rank_m, df, config, avg_turnover_dict, atr_dict, liquidity_mask_dict, bench_regime_arr)
                    results.append(res)
                    print(f"[{run_count:02d}/{total_runs:02d}] Entry SMA: {entry:2d} | Exit SMA: {exit_s:2d} | Rank: {rank_m:8s} | Return: {res['abs_return']:6.2f}% | CAGR: {res['cagr']:6.2f}% | DD: {res['max_dd']:6.2f}% | Ratio: {res['ret_dd_ratio']:.2f}", flush=True)
                except Exception as e:
                    print(f"[ERR] [{run_count:02d}/{total_runs:02d}] Failed for Entry: {entry}, Exit: {exit_s}, Rank: {rank_m}: {e}", flush=True)
                    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(by='cagr', ascending=False)
    
    print("\n" + "="*90, flush=True)
    print("                      OPTIMIZATION GRID SEARCH RESULTS (TOP 10)", flush=True)
    print("="*90, flush=True)
    headers = ["Entry SMA", "Exit SMA", "Rank By", "Abs Return", "CAGR", "Max DD", "Ret/DD", "Trades", "Win Rate"]
    print(f"{headers[0]:10s} {headers[1]:10s} {headers[2]:10s} {headers[3]:11s} {headers[4]:8s} {headers[5]:8s} {headers[6]:8s} {headers[7]:6s} {headers[8]:8s}", flush=True)
    print("-"*90, flush=True)
    for _, row in results_df.head(10).iterrows():
        print(f"{int(row['entry_sma']):10d} {int(row['exit_sma']):10d} {row['ranking_method']:10s} {row['abs_return']:10.2f}% {row['cagr']:7.2f}% {row['max_dd']:7.2f}% {row['ret_dd_ratio']:8.2f} {int(row['trades']):6d} {row['win_rate']:7.2f}%", flush=True)
    print("="*90 + "\n", flush=True)
    
    results_df.to_csv("basso_optimization_results.csv", index=False)
    print("[OK] Optimization results saved to basso_optimization_results.csv", flush=True)

if __name__ == "__main__":
    main()
