import pandas as pd
import numpy as np
import itertools
from core import DataManager, MomentumStrategy, ConfigLoader
from backtest import SimplePortfolio
import os
from tqdm import tqdm

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
    # Initialize components
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
    
    # Pre-calculate data needed for this lookback
    momentum_df = data_mgr.calculate_momentum(lookback_days=params['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=params['momentum_lookback_days'])
    
    # Regime data
    bench_dma = bench_prices.rolling(window=200).mean() if bench_prices is not None else None
    bench_roc = bench_prices.pct_change(60) if bench_prices is not None else None

    # Resample
    monthly_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
    
    if params.get('skip_latest_period', False):
        monthly_momentum = monthly_momentum.shift(1).dropna(how='all')

    prices = data_mgr.prices

    for date, momentum_row in monthly_momentum.iterrows():
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]

        # Determine Market Regime
        is_bull_market = True
        if params['regime_filter'] == '200dma' and bench_dma is not None:
            is_bull_market = bench_prices.loc[:date].iloc[-1] > bench_dma.loc[:date].iloc[-1]
        elif params['regime_filter'] == '60roc' and bench_roc is not None:
            is_bull_market = bench_roc.loc[:date].iloc[-1] > 0
        
        current_gold_price = None
        if gold_prices is not None and not gold_prices.empty:
            try:
                current_gold_price = gold_prices.loc[:date].iloc[-1]
            except:
                pass

        liquidate_on_bear = params.get('liquidate_on_bear_market', False)
        current_holdings = list(portfolio.positions.keys())  
        
        if not is_bull_market and liquidate_on_bear:
            target_portfolio = []
        else:
            target_portfolio = strategy.get_target_portfolio(
                momentum_row, 
                current_holdings, 
                current_prices, 
                current_highs,
                market_bullish=is_bull_market)
        
        portfolio.update_portfolio(date, target_portfolio, current_prices, current_gold_price)
    
    results_df = portfolio.get_equity_curve()
    return results_df, portfolio.total_trades

def main():
    # 1. Load Baseline Config
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    bt_cfg = cfg.get_backtest_params()
    
    bt_start = bt_cfg.get("start_date", "2016-01-01")
    bt_end = bt_cfg.get("end_date", "2026-01-01")
    
    # 2. Load Data once
    symbols_df = pd.read_csv(paths['symbols_file'])
    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    
    data_mgr = DataManager(
        universe, 
        start_date=bt_start, 
        end_date=bt_end, 
        cache_filename=paths['master_data_file'],
        live_mode=False
    )
    
    print("Loading data...")
    data_mgr.fetch_data()
    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    gold_prices = data_mgr.fetch_benchmark("GOLDBEES.NS")
    
    # Benchmark metrics for Alpha calculation
    sliced_bench = bench_prices.loc[bt_start:bt_end].dropna() if bench_prices is not None else None
    
    # 3. Define Parameter Grid
    grid = {
        'momentum_lookback_days': [60, 90],
        'skip_latest_period': [True],
        'portfolio_size': [10, 15],
        'drawdown_limit': [0.10, 0.12, 0.15],
        'exit_rank': [30, 50],
        'regime_filter': ['200dma', '60roc'],
        'liquidate_on_bear_market': [True],
        'allocate_in_gold': [True, False]
    }
    
    # Fixed parameters
    entry_rank = 10
    initial_capital_per_slot = cap_cfg['allocation_per_slot']
    liquid_yield = cap_cfg.get('liquid_etf_yield', 0.065)
    rebalance_freq = cap_cfg.get('rebalance_frequency', 'W-FRI')
    
    # Generate combinations
    keys, values = zip(*grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"Starting grid search over {len(combinations)} combinations...")
    
    all_results = []
    
    for i, params in enumerate(tqdm(combinations)):
        # Inject fixed params
        params['entry_rank'] = entry_rank
        
        try:
            results_df, total_trades = run_single_backtest(
                params, data_mgr, bench_prices, gold_prices, 
                bt_start, bt_end, initial_capital_per_slot, 
                liquid_yield, rebalance_freq
            )
            
            initial_cap = initial_capital_per_slot * params['portfolio_size']
            metrics = calculate_metrics(results_df['Total Equity'], initial_cap, bt_start, bt_end, sliced_bench)
            
            # Record result
            res = params.copy()
            res.update(metrics)
            res['Total Trades'] = total_trades
            all_results.append(res)
        except Exception as e:
            print(f"Error in combination {i}: {e}")
            continue
            
    # 4. Save and Sort
    df_results = pd.DataFrame(all_results)
    if not df_results.empty:
        df_results = df_results.sort_values(by='Ret/DD Ratio', ascending=False)
        output_file = 'results/optimization_results.csv'
        os.makedirs('results', exist_ok=True)
        df_results.to_csv(output_file, index=False)
        print(f"\nOptimization complete! Results saved to {output_file}")
        print("\nTop 5 Configurations:")
        print(df_results.head(5).to_string(index=False))
    else:
        print("No results generated.")

if __name__ == "__main__":
    main()
