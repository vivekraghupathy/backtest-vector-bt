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

def main():
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
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
    
    # 150DMA Logic
    bench_dma_window = 150
    bench_dma = bench_prices.rolling(window=bench_dma_window).mean()

    # AGGRESSIVE PARAMS FROM CONFIG
    params = {
        'momentum_lookback_days': strat_cfg['momentum_lookback_days'],
        'skip_latest_period': strat_cfg['skip_latest_period'],
        'portfolio_size': strat_cfg['portfolio_size'],
        'drawdown_limit': strat_cfg['drawdown_limit'],
        'exit_rank': strat_cfg['exit_rank'],
        'entry_rank': strat_cfg['entry_rank'],
        'liquidate_on_bear_market': True,
        'allocate_in_gold': True
    }

    strategy = MomentumStrategy(
        portfolio_size=params['portfolio_size'],
        entry_rank=params['entry_rank'],
        exit_rank=params['exit_rank'],
        drawdown_limit=params['drawdown_limit'],
        verbose=False
    )
    portfolio = SimplePortfolio(
        portfolio_size=params['portfolio_size'],
        initial_capital=cap_cfg['allocation_per_slot'] * params['portfolio_size'],
        liquid_yield=cap_cfg.get('liquid_etf_yield', 0.065)
    )
    portfolio.allocate_in_gold = params['allocate_in_gold']
    
    momentum_df = data_mgr.calculate_momentum(lookback_days=params['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=params['momentum_lookback_days'])
    
    rebalance_freq = 'W-FRI'
    weekly_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
    if params.get('skip_latest_period', False):
        weekly_momentum = weekly_momentum.shift(1).dropna(how='all')
    
    prices = data_mgr.prices
    print(f"Running Backtest (Aggressive with {bench_dma_window}DMA Regime Filter)...")
    for date, momentum_row in weekly_momentum.iterrows():
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]
        
        # Determine Market Regime using 150DMA
        is_bull_market = True
        if bench_prices is not None and not bench_prices.empty:
            try:
                bench_price = bench_prices.loc[:date].iloc[-1]
                bench_ma = bench_dma.loc[:date].iloc[-1]
                is_bull_market = bench_price > bench_ma
            except:
                is_bull_market = True
        
        current_gold_price = None
        if gold_prices is not None and not gold_prices.empty:
            try:
                current_gold_price = gold_prices.loc[:date].iloc[-1]
            except: pass

        current_holdings = list(portfolio.positions.keys())  
        
        if not is_bull_market and params['liquidate_on_bear_market']:
            target_portfolio = []
        else:
            target_portfolio = strategy.get_target_portfolio(
                momentum_row, current_holdings, current_prices, current_highs, market_bullish=is_bull_market
            )
        portfolio.update_portfolio(date, target_portfolio, current_prices, current_gold_price)
    
    curve = portfolio.get_equity_curve()
    metrics = calculate_metrics(curve['Total Equity'], cap_cfg['allocation_per_slot'] * params['portfolio_size'], bt_start, bt_end, sliced_bench)
    
    print("\n" + "="*60)
    print(f"BACKTEST RESULT: AGGRESSIVE ({bench_dma_window}DMA REGIME FILTER)")
    print("="*60)
    for k, v in metrics.items():
        print(f"{k:<15}: {v}")
    print(f"{'Total Trades':<15}: {portfolio.total_trades}")
    print("="*60)

if __name__ == "__main__":
    main()
