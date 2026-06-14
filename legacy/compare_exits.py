import pandas as pd
import numpy as np
from core import DataManager, MomentumStrategy, ConfigLoader
from backtest import SimplePortfolio
import os

def calculate_metrics(equity_curve, initial_capital, start_date, end_date, bench_series=None):
    if equity_curve.empty:
        return {}
    final_equity = equity_curve.iloc[-1]
    abs_return = ((final_equity - initial_capital) / initial_capital) * 100
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    years = (end_dt - start_dt).days / 365.25
    cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_dd = drawdown.min() * 100
    metrics = {
        'Abs Return %': round(abs_return, 2),
        'CAGR %': round(cagr, 2),
        'Max DD %': round(max_dd, 2),
        'Ret/DD Ratio': round(abs(cagr / max_dd), 2) if max_dd != 0 else 0
    }
    if bench_series is not None and not bench_series.empty:
        bench_start = bench_series.iloc[0]
        bench_end = bench_series.iloc[-1]
        bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
        metrics['Alpha %'] = round(cagr - bench_cagr, 2)
    return metrics

def run_single_backtest(params, data_mgr, bench_prices, gold_prices, bt_start, bt_end, initial_capital_per_slot, liquid_yield, rebalance_freq):
    strategy = MomentumStrategy(
        portfolio_size=params['portfolio_size'],
        entry_rank=params['entry_rank'],
        exit_rank=params['exit_rank'],
        drawdown_limit=params['drawdown_limit'],
        verbose=False
    )
    portfolio = SimplePortfolio(
        portfolio_size=params['portfolio_size'],
        initial_capital=initial_capital_per_slot * params['portfolio_size'],
        liquid_yield=liquid_yield
    )
    portfolio.allocate_in_gold = params.get('allocate_in_gold', False)
    momentum_df = data_mgr.calculate_momentum(lookback_days=params['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=params['momentum_lookback_days'])
    bench_dma = bench_prices.rolling(window=200).mean() if bench_prices is not None else None
    
    # Weekly rebalance
    weekly_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
    if params.get('skip_latest_period', False):
        weekly_momentum = weekly_momentum.shift(1).dropna(how='all')
    
    prices = data_mgr.prices
    for date, momentum_row in weekly_momentum.iterrows():
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]
        
        # 200DMA Regime Filter
        is_bull_market = True
        if bench_dma is not None:
            is_bull_market = bench_prices.loc[:date].iloc[-1] > bench_dma.loc[:date].iloc[-1]
        
        current_gold_price = None
        if gold_prices is not None and not gold_prices.empty:
            try:
                current_gold_price = gold_prices.loc[:date].iloc[-1]
            except: pass
            
        liquidate_on_bear = params.get('liquidate_on_bear_market', False)
        current_holdings = list(portfolio.positions.keys())  
        
        if not is_bull_market and liquidate_on_bear:
            target_portfolio = []
        else:
            target_portfolio = strategy.get_target_portfolio(
                momentum_row, current_holdings, current_prices, current_highs, market_bullish=is_bull_market
            )
        portfolio.update_portfolio(date, target_portfolio, current_prices, current_gold_price)
    
    return portfolio.get_equity_curve(), portfolio.total_trades

def main():
    cfg = ConfigLoader('config.json')
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    bt_cfg = cfg.get_backtest_params()
    bt_start, bt_end = bt_cfg.get("start_date", "2016-01-01"), bt_cfg.get("end_date", "2026-01-01")
    
    symbols_df = pd.read_csv(paths['symbols_file'])
    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    
    data_mgr = DataManager(universe, start_date=bt_start, end_date=bt_end, cache_filename=paths['master_data_file'], live_mode=False)
    print("Loading data...")
    data_mgr.fetch_data()
    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    gold_prices = data_mgr.fetch_benchmark("GOLDBEES.NS")
    sliced_bench = bench_prices.loc[bt_start:bt_end].dropna() if bench_prices is not None else None
    
    rebalance_freq = 'W-FRI'
    
    exit_tests = [0.08, 0.10, 0.12]
    results = []
    
    for sl in exit_tests:
        name = f"Aggressive ({int(sl*100)}% SL)"
        print(f"Running {name}...")
        params = {
            'momentum_lookback_days': 60, 'skip_latest_period': True, 'portfolio_size': 10,
            'drawdown_limit': sl, 'exit_rank': 50, 'entry_rank': 10,
            'liquidate_on_bear_market': True, 'allocate_in_gold': True
        }
        curve, trades = run_single_backtest(params, data_mgr, bench_prices, gold_prices, bt_start, bt_end, cap_cfg['allocation_per_slot'], cap_cfg.get('liquid_etf_yield', 0.065), rebalance_freq)
        metrics = calculate_metrics(curve['Total Equity'], cap_cfg['allocation_per_slot'] * params['portfolio_size'], bt_start, bt_end, sliced_bench)
        metrics['Strategy'] = name
        metrics['Total Trades'] = trades
        results.append(metrics)
    
    df = pd.DataFrame(results)
    print("\n" + "="*60)
    print("STOP LOSS (DRAWDOWN LIMIT) COMPARISON - 10 YEARS")
    print("="*60)
    print(df[['Strategy', 'CAGR %', 'Max DD %', 'Ret/DD Ratio', 'Alpha %', 'Total Trades']].to_string(index=False))
    print("="*60)

if __name__ == "__main__":
    main()
