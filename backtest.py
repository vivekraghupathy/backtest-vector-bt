import matplotlib.pyplot as plt
import pandas as pd
import math
import re
from core import DataManager, MomentumStrategy, ConfigLoader
from analytics import TradeAnalyzer, convert_journal_to_ledger, calculate_metrics

class SimplePortfolio:
    def __init__(self, portfolio_size, initial_capital=1000000, transaction_cost_pct=0.0001, equity_tax_rate=0.0, cash_tax_rate=0.0, liquid_yield=0.0):
        self.portfolio_size = portfolio_size
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}          # Dictionary of {ticker: shares}
        self.buy_prices = {}         # Dictionary of {ticker: entry_price}
        self.total_trades = 0
        self.equity_history = []     # To store equity curve data
        self.liquid_yield = liquid_yield
        self.last_date = None
        self.last_gold_price = None
        self.allocate_in_gold = False  
        self.gold_weight = 0.0             
        self.backtest_journal = []   # To log all BUY/SELL actions
        
        # Friction Parameters
        self.transaction_cost_pct = transaction_cost_pct
        self.equity_tax_rate = equity_tax_rate
        self.cash_tax_rate = cash_tax_rate

    def update_portfolio(self, date, target_tickers, current_prices, current_gold_price=None):
        """
        Executes weekly/monthly trades: liquidates dropped positions and buys new ones
        with a budget of (Total Equity / Portfolio Size) per slot.
        """
        positions_value = sum(self.positions[t] * current_prices.get(t, 0) for t in self.positions)
        current_total_equity = self.cash + positions_value
        allocation_per_slot = current_total_equity / self.portfolio_size

        # Add yield on uninvested cash (if yield is enabled)
        if self.last_date is not None and self.liquid_yield > 0:
            days_passed = (date - self.last_date).days
            if days_passed > 0:
                liquid_return = self.liquid_yield * (days_passed / 365.0)
                if self.allocate_in_gold and self.last_gold_price and current_gold_price and self.last_gold_price > 0:
                    gold_return = (current_gold_price - self.last_gold_price) / self.last_gold_price
                    blended_return = ((1 - self.gold_weight) * liquid_return) + (self.gold_weight * gold_return)
                else:
                    blended_return = liquid_return

                interest = self.cash * blended_return
                taxed_interest = interest * (1 - self.cash_tax_rate)
                self.cash += taxed_interest 
                   
        self.last_date = date
        self.last_gold_price = current_gold_price

        # 1. SELL PHASE: Complete liquidation of stocks no longer in target
        for ticker in list(self.positions.keys()):
            if ticker not in target_tickers:
                shares = self.positions.pop(ticker)
                buy_price = self.buy_prices.pop(ticker, 0)
                price = current_prices.get(ticker)
                
                if pd.notna(price):
                    gross_proceeds = shares * price
                    gain = gross_proceeds - (shares * buy_price)
                    tax = max(0.0, gain * self.equity_tax_rate)
                    comm = gross_proceeds * self.transaction_cost_pct
                    net_proceeds = gross_proceeds - tax - comm
                    
                    self.cash += net_proceeds
                    self.total_trades += 1
                    self.backtest_journal.append([
                        date, 'SELL', ticker, shares, round(price, 2), round(net_proceeds, 2)
                    ])

        # 2. BUY PHASE: Allocate fixed slot budget to brand new entries only
        for ticker in target_tickers:
            if ticker not in self.positions:
                price = current_prices.get(ticker)
                if pd.notna(price) and price > 0:
                    shares_to_buy = math.floor(allocation_per_slot / price)
                    if shares_to_buy > 0:
                        gross_cost = shares_to_buy * price
                        comm = gross_cost * self.transaction_cost_pct
                        total_cost = gross_cost + comm
                        
                        if self.cash >= total_cost:
                            self.cash -= total_cost
                              
                            self.positions[ticker] = shares_to_buy
                            self.buy_prices[ticker] = price
                            self.backtest_journal.append([
                                date, 'BUY', ticker, shares_to_buy, round(price, 2), round(total_cost, 2)
                              ])

        # 3. LOGGING
        positions_value = sum(self.positions[t] * current_prices.get(t, 0) for t in self.positions)
        total_equity = self.cash + positions_value
        holdings_str = ", ".join([f"{t}: {s}" for t, s in self.positions.items()]) if self.positions else "Cash"

        self.equity_history.append({
            'Date': date,
            'Total Equity': total_equity,
            'Cash': self.cash,
            'Invested Value': positions_value,
            'Active Positions': len(self.positions),
            'Holdings': holdings_str
        })

    def get_equity_curve(self):
        df = pd.DataFrame(self.equity_history)
        if not df.empty:
            df.set_index('Date', inplace=True)
        return df


class BarbellPortfolio:
    def __init__(self, gold_ratio_in_safe, risk_portfolio_size, initial_capital=1000000, transaction_cost_pct=0.0001, equity_tax_rate=0.0, cash_tax_rate=0.0, liquid_yield=0.0):
        self.gold_ratio_in_safe = gold_ratio_in_safe
        self.risk_portfolio_size = risk_portfolio_size
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}          # Dictionary of {ticker: shares} (momentum stocks)
        self.gold_shares = 0         # Explicit Gold shares (GOLDBEES.NS)
        self.buy_prices = {}         # Dictionary of {ticker: entry_price} for momentum stocks
        self.total_trades = 0
        self.equity_history = []     # To store equity curve data
        self.liquid_yield = liquid_yield
        self.last_date = None
        self.backtest_journal = []   # To log all BUY/SELL actions
        
        # Friction Parameters
        self.transaction_cost_pct = transaction_cost_pct
        self.equity_tax_rate = equity_tax_rate
        self.cash_tax_rate = cash_tax_rate

    def update_portfolio(self, date, target_tickers, current_prices, safe_weight, current_gold_price=None, active_gold_ratio=None):
        # 1. Re-value portfolio
        stocks_value = sum(self.positions[t] * current_prices.get(t, 0) for t in self.positions)
        gold_value = self.gold_shares * current_gold_price if (self.gold_shares > 0 and current_gold_price is not None) else 0.0
        current_total_equity = self.cash + stocks_value + gold_value

        # 2. Add yield on Cash balance
        if self.last_date is not None and self.liquid_yield > 0:
            days_passed = (date - self.last_date).days
            if days_passed > 0:
                liquid_return = self.liquid_yield * (days_passed / 365.0)
                interest = self.cash * liquid_return
                taxed_interest = interest * (1 - self.cash_tax_rate)
                self.cash += taxed_interest
                # Recalculate total equity with new cash
                current_total_equity = self.cash + stocks_value + gold_value
                
        self.last_date = date

        # 3. Calculate target weights and values
        target_safe_value = current_total_equity * safe_weight
        target_risk_value = current_total_equity * (1 - safe_weight)
        
        if active_gold_ratio is None:
            active_gold_ratio = self.gold_ratio_in_safe
        target_gold_value = target_safe_value * active_gold_ratio
        
        allocation_per_slot = target_risk_value / self.risk_portfolio_size if self.risk_portfolio_size > 0 else 0.0

        # 4. SELL PHASE: Stocks no longer in target
        for ticker in list(self.positions.keys()):
            if ticker not in target_tickers:
                shares = self.positions.pop(ticker)
                buy_price = self.buy_prices.pop(ticker, 0)
                price = current_prices.get(ticker)
                
                if pd.notna(price):
                    gross_proceeds = shares * price
                    gain = gross_proceeds - (shares * buy_price)
                    tax = max(0.0, gain * self.equity_tax_rate)
                    comm = gross_proceeds * self.transaction_cost_pct
                    net_proceeds = gross_proceeds - tax - comm
                    
                    self.cash += net_proceeds
                    self.total_trades += 1
                    self.backtest_journal.append([
                        date, 'SELL', ticker, shares, round(price, 2), round(net_proceeds, 2)
                    ])

        # 5. ADJUST GOLD POSITION (GOLDBEES.NS)
        if current_gold_price is not None and pd.notna(current_gold_price) and current_gold_price > 0:
            target_gold_shares = math.floor(target_gold_value / current_gold_price)
            gold_diff_shares = target_gold_shares - self.gold_shares
            
            if gold_diff_shares > 0:
                # BUY GOLD
                gross_cost = gold_diff_shares * current_gold_price
                comm = gross_cost * self.transaction_cost_pct
                total_cost = gross_cost + comm
                if self.cash >= total_cost:
                    self.cash -= total_cost
                    self.gold_shares += gold_diff_shares
                    self.total_trades += 1
                    self.backtest_journal.append([
                        date, 'BUY', 'GOLDBEES.NS', gold_diff_shares, round(current_gold_price, 2), round(total_cost, 2)
                    ])
            elif gold_diff_shares < 0:
                # SELL GOLD
                gold_shares_to_sell = abs(gold_diff_shares)
                gross_proceeds = gold_shares_to_sell * current_gold_price
                comm = gross_proceeds * self.transaction_cost_pct
                net_proceeds = gross_proceeds - comm
                
                self.cash += net_proceeds
                self.gold_shares -= gold_shares_to_sell
                self.total_trades += 1
                self.backtest_journal.append([
                    date, 'SELL', 'GOLDBEES.NS', gold_shares_to_sell, round(current_gold_price, 2), round(net_proceeds, 2)
                ])

        # 6. BUY PHASE: Momentum Stocks (brand new entries only)
        for ticker in target_tickers:
            if ticker not in self.positions:
                price = current_prices.get(ticker)
                if pd.notna(price) and price > 0:
                    shares_to_buy = math.floor(allocation_per_slot / price)
                    if shares_to_buy > 0:
                        gross_cost = shares_to_buy * price
                        comm = gross_cost * self.transaction_cost_pct
                        total_cost = gross_cost + comm
                        
                        if self.cash >= total_cost:
                            self.cash -= total_cost
                            self.positions[ticker] = shares_to_buy
                            self.buy_prices[ticker] = price
                            self.total_trades += 1
                            self.backtest_journal.append([
                                date, 'BUY', ticker, shares_to_buy, round(price, 2), round(total_cost, 2)
                            ])

        # 7. LOG STATE
        stocks_value = sum(self.positions[t] * current_prices.get(t, 0) for t in self.positions)
        gold_value = self.gold_shares * current_gold_price if (self.gold_shares > 0 and current_gold_price is not None) else 0.0
        total_equity = self.cash + stocks_value + gold_value
        
        holdings_list = []
        if self.gold_shares > 0:
            holdings_list.append(f"GOLDBEES.NS: {self.gold_shares}")
        for t, s in self.positions.items():
            holdings_list.append(f"{t}: {s}")
        holdings_str = ", ".join(holdings_list) if holdings_list else "Cash"

        self.equity_history.append({
            'Date': date,
            'Total Equity': total_equity,
            'Cash': self.cash,
            'Invested Value': stocks_value + gold_value,
            'Active Positions': len(self.positions) + (1 if self.gold_shares > 0 else 0),
            'Holdings': holdings_str
        })

    def get_equity_curve(self):
        df = pd.DataFrame(self.equity_history)
        if not df.empty:
            df.set_index('Date', inplace=True)
        return df


def plot_backtest_results(momentum_df, barbell_df, bench_series=None, bench_ticker="Benchmark"):
    """
    Generates a comparison plot showing Momentum and Barbell Total Equity growth and cash levels over time.
    """
    plt.style.use('seaborn-v0_8-darkgrid')
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                   gridspec_kw={'height_ratios': [3, 1]}, 
                                   sharex=True)
    
    # --- Top Subplot: Total Equity ---
    if momentum_df is not None and not momentum_df.empty:
        momentum_df.index = pd.to_datetime(momentum_df.index)
        ax1.plot(momentum_df.index, momentum_df['Total Equity'], 
                 label='Momentum Strategy', color='#1f77b4', linewidth=2)
                 
    if barbell_df is not None and not barbell_df.empty:
        barbell_df.index = pd.to_datetime(barbell_df.index)
        ax1.plot(barbell_df.index, barbell_df['Total Equity'], 
                 label='Barbell Strategy', color='#2ca02c', linewidth=2)
                 
    if bench_series is not None and not bench_series.empty:
        bench_series.index = pd.to_datetime(bench_series.index)
        ax1.plot(bench_series.index, bench_series, 
                 label=f'Benchmark ({bench_ticker})', color='#ff7f0e', linewidth=1.5, linestyle='--')
                 
    ax1.set_title('Strategy Comparison (Equity Growth)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Equity (INR)', fontsize=12)
    ax1.yaxis.set_major_formatter(plt.matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
    ax1.legend(loc='upper left')
    
    # --- Bottom Subplot: Cash Balance ---
    if momentum_df is not None and not momentum_df.empty:
        ax2.plot(momentum_df.index, momentum_df['Cash'], label='Momentum Cash', color='#1f77b4', linewidth=1, alpha=0.6)
    if barbell_df is not None and not barbell_df.empty:
        ax2.plot(barbell_df.index, barbell_df['Cash'], label='Barbell Cash', color='#2ca02c', linewidth=1, alpha=0.6)
        
    ax2.set_xlabel('Date', fontsize=12)
    ax2.set_ylabel('Cash (INR)', fontsize=12)
    ax2.yaxis.set_major_formatter(plt.matplotlib.ticker.StrMethodFormatter('{x:,.0f}'))
    ax2.legend(loc='upper left')
    
    plt.tight_layout()
    plt.show()


def print_run_summary_comparison(momentum_df, momentum_trades, barbell_df, barbell_trades, initial_capital, start_date, end_date, bench_series=None, bench_ticker="Benchmark"):
    """Calculates and prints the final backtest comparison metrics."""
    if momentum_df.empty or barbell_df.empty:
        print("Error: Empty dataframes received.")
        return
        
    m_metrics = calculate_metrics(momentum_df['Total Equity'], initial_capital, start_date, end_date, bench_series)
    b_metrics = calculate_metrics(barbell_df['Total Equity'], initial_capital, start_date, end_date, bench_series)
    
    if bench_series is not None and not bench_series.empty:
        years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
        bench_start = bench_series.iloc[0]
        bench_end = bench_series.iloc[-1]
        bench_abs_return = ((bench_end - bench_start) / bench_start) * 100
        bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
        rolling_max_bench = bench_series.cummax()
        drawdown_bench = (bench_series - rolling_max_bench) / rolling_max_bench
        max_dd_bench = drawdown_bench.min() * 100
    else:
        bench_abs_return, bench_cagr, max_dd_bench = 0.0, 0.0, 0.0

    print("\n" + "="*80)
    print(f"PARALLEL STRATEGY COMPARISON: {start_date} to {end_date}")
    print("="*80)
    print(f"Initial Capital:   INR {initial_capital:,.2f}")
    print(f"Momentum Final:    INR {momentum_df['Total Equity'].iloc[-1]:,.2f}")
    print(f"Barbell Final:     INR {barbell_df['Total Equity'].iloc[-1]:,.2f}")
    print("-" * 80)
    print(f"{'PERFORMANCE':<18} | {'Momentum':<15} | {'Barbell':<15} | {'Benchmark (' + bench_ticker + ')':<20}")
    print("-" * 80)
    print(f"{'Absolute Return':<18} | {m_metrics['Abs Return %']:>13.2f}% | {b_metrics['Abs Return %']:>13.2f}% | {bench_abs_return:>18.2f}%")
    print(f"{'CAGR':<18} | {m_metrics['CAGR %']:>13.2f}% | {b_metrics['CAGR %']:>13.2f}% | {bench_cagr:>18.2f}%")
    print(f"{'Max Drawdown':<18} | {m_metrics['Max DD %']:>13.2f}% | {b_metrics['Max DD %']:>13.2f}% | {max_dd_bench:>18.2f}%")
    print(f"{'Total Trades':<18} | {momentum_trades:>14} | {barbell_trades:>14} | {'-':>20}")
    print("-" * 80)
    print(f"{'ALPHA (CAGR Diff)':<18} | [ {m_metrics.get('Alpha %', 0.0):+.2f}% ]      | [ {b_metrics.get('Alpha %', 0.0):+.2f}% ]      | {'-':>20}")
    print("="*80 + "\n")


def run_single_backtest(params, data_mgr, bench_prices, gold_prices, bt_start, bt_end, initial_capital_per_slot, liquid_yield, rebalance_freq):
    # Initialize strategy
    strategy = MomentumStrategy(
        portfolio_size=params['portfolio_size'],
        entry_rank=params['entry_rank'],
        exit_rank=params['exit_rank'],
        drawdown_limit=params['drawdown_limit'],
        verbose=False
    )
    
    # Initialize simplified portfolio
    portfolio = SimplePortfolio(
        portfolio_size=params['portfolio_size'],
        initial_capital=initial_capital_per_slot * params['portfolio_size'],
        transaction_cost_pct=params.get('transaction_cost_pct', 0.0001),
        equity_tax_rate=params.get('equity_tax_rate', 0.0),
        cash_tax_rate=params.get('cash_tax_rate', 0.0),
        liquid_yield=liquid_yield
    )
    
    portfolio.allocate_in_gold = params.get('allocate_in_gold', False)
    portfolio.gold_weight = params.get('gold_weight', 1.0)
    
    # Pre-calculate data needed
    momentum_df = data_mgr.calculate_momentum(lookback_days=params['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=params['momentum_lookback_days'])
    
    # Resample momentum to the specified frequency
    weekly_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
    if params.get('skip_latest_period', False):
        weekly_momentum = weekly_momentum.shift(1).dropna(how='all')
        
    # Precalculate Benchmark Regime filters
    bench_dma = None
    bench_roc = None
    bench_highs = None
    bench_lows = None
    regime_filter = params.get('regime_filter', '200dma')
    
    if regime_filter and regime_filter != 'none' and bench_prices is not None:
        if 'dma' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            window = int(match.group()) if match else 200
            bench_dma = bench_prices.rolling(window=window).mean()
        elif 'roc' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            lookback = int(match.group()) if match else 60
            bench_roc = bench_prices.pct_change(periods=lookback)
        elif 'breakout' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            window = int(match.group()) if match else 50
            bench_highs = bench_prices.shift(1).rolling(window=window).max()
            bench_lows = bench_prices.shift(1).rolling(window=window).min()

    # Precalculate ADX trend strength filter
    bench_adx = None
    use_adx_filter = params.get('use_adx_filter', False)
    adx_threshold = params.get('adx_threshold', 20)
    
    if use_adx_filter and bench_prices is not None:
        adx_window = params.get('adx_window', 14)
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

    prices = data_mgr.prices
    is_bull_market = True
    
    for date, momentum_row in weekly_momentum.iterrows():
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]

        # Determine Market Regime (Bullish vs Bearish)
        if regime_filter and regime_filter != 'none' and bench_prices is not None:
            try:
                if bench_dma is not None:
                    is_bull_market = bench_prices.loc[:date].iloc[-1] > bench_dma.loc[:date].iloc[-1]
                elif bench_roc is not None:
                    is_bull_market = bench_roc.loc[:date].iloc[-1] > 0
                elif bench_highs is not None and bench_lows is not None:
                    curr_price = bench_prices.loc[:date].iloc[-1]
                    curr_high = bench_highs.loc[:date].iloc[-1]
                    curr_low = bench_lows.loc[:date].iloc[-1]
                    if pd.notna(curr_price) and pd.notna(curr_high) and pd.notna(curr_low):
                        if curr_price > curr_high:
                            is_bull_market = True
                        elif curr_price < curr_low:
                            is_bull_market = False
            except Exception:
                pass
        
        # Determine if trending (ADX filter)
        is_trending = True
        if bench_adx is not None:
            try:
                is_trending = bench_adx.loc[:date].iloc[-1] >= adx_threshold
            except Exception:
                is_trending = True
                
        allow_new_entries = is_bull_market and is_trending
        
        current_gold_price = None
        if gold_prices is not None and not gold_prices.empty:
            try:
                current_gold_price = gold_prices.loc[:date].iloc[-1]
            except Exception:
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
                market_bullish=allow_new_entries
            )
        
        portfolio.update_portfolio(date, target_portfolio, current_prices, current_gold_price)
        
    return portfolio.get_equity_curve(), portfolio


def run_single_barbell_backtest(params, data_mgr, bench_prices, gold_prices, bt_start, bt_end, initial_capital, liquid_yield, rebalance_freq):
    # Initialize strategy
    strategy = MomentumStrategy(
        portfolio_size=params['risk_portfolio_size'],
        entry_rank=params['entry_rank'],
        exit_rank=params['exit_rank'],
        drawdown_limit=params['drawdown_limit'],
        verbose=False
    )
    
    # Initialize barbell portfolio
    portfolio = BarbellPortfolio(
        gold_ratio_in_safe=params['gold_ratio_in_safe'],
        risk_portfolio_size=params['risk_portfolio_size'],
        initial_capital=initial_capital,
        transaction_cost_pct=params.get('transaction_cost_pct', 0.0001),
        equity_tax_rate=params.get('equity_tax_rate', 0.0),
        cash_tax_rate=params.get('cash_tax_rate', 0.0),
        liquid_yield=liquid_yield
    )
    
    # Pre-calculate data needed
    momentum_df = data_mgr.calculate_momentum(lookback_days=params['momentum_lookback_days'])
    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=params['momentum_lookback_days'])
    
    # Resample momentum to the specified frequency
    weekly_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
    if params.get('skip_latest_period', False):
        weekly_momentum = weekly_momentum.shift(1).dropna(how='all')
        
    # Precalculate Benchmark Regime filters
    bench_dma = None
    bench_roc = None
    bench_highs = None
    bench_lows = None
    regime_filter = params.get('regime_filter', '200dma')
    
    if regime_filter and regime_filter != 'none' and bench_prices is not None:
        if 'dma' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            window = int(match.group()) if match else 200
            bench_dma = bench_prices.rolling(window=window).mean()
        elif 'roc' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            lookback = int(match.group()) if match else 60
            bench_roc = bench_prices.pct_change(periods=lookback)
        elif 'breakout' in str(regime_filter):
            match = re.search(r'\d+', str(regime_filter))
            window = int(match.group()) if match else 50
            bench_highs = bench_prices.shift(1).rolling(window=window).max()
            bench_lows = bench_prices.shift(1).rolling(window=window).min()

    # Precalculate Gold Trend filters
    gold_ma = None
    gold_trend_filter = params.get('gold_trend_filter', False)
    gold_trend_lookback = params.get('gold_trend_lookback_days', 50)
    if gold_trend_filter and gold_prices is not None and not gold_prices.empty:
        gold_ma = gold_prices.rolling(window=gold_trend_lookback).mean()

    prices = data_mgr.prices
    is_bull_market = True
    
    for date, momentum_row in weekly_momentum.iterrows():
        current_prices = prices.loc[:date].iloc[-1] 
        current_highs = rolling_highs_df.loc[:date].iloc[-1]
        
        # Determine Market Regime
        if regime_filter and regime_filter != 'none' and bench_prices is not None:
            try:
                if bench_dma is not None:
                    is_bull_market = bench_prices.loc[:date].iloc[-1] > bench_dma.loc[:date].iloc[-1]
                elif bench_roc is not None:
                    is_bull_market = bench_roc.loc[:date].iloc[-1] > 0
                elif bench_highs is not None and bench_lows is not None:
                    curr_price = bench_prices.loc[:date].iloc[-1]
                    curr_high = bench_highs.loc[:date].iloc[-1]
                    curr_low = bench_lows.loc[:date].iloc[-1]
                    if pd.notna(curr_price) and pd.notna(curr_high) and pd.notna(curr_low):
                        if curr_price > curr_high:
                            is_bull_market = True
                        elif curr_price < curr_low:
                            is_bull_market = False
            except Exception:
                pass

        current_gold_price = None
        is_gold_bullish = True
        if gold_prices is not None and not gold_prices.empty:
            try:
                current_gold_price = gold_prices.loc[:date].iloc[-1]
                if gold_ma is not None:
                    is_gold_bullish = current_gold_price > gold_ma.loc[:date].iloc[-1]
            except Exception:
                pass

        current_holdings = list(portfolio.positions.keys())  
        
        # Barbell Strategy ignores the regime filter completely for momentum stock trading
        target_portfolio = strategy.get_target_portfolio(
            momentum_row, 
            current_holdings, 
            current_prices, 
            current_highs,
            market_bullish=True
        )
        
        # Determine safe weight based on regime
        safe_weight = params['safe_weight_bull'] if is_bull_market else params['safe_weight_bear']
        
        # Determine gold allocation weight based on gold trend
        active_gold_ratio = params['gold_ratio_in_safe'] if is_gold_bullish else 0.0
        
        portfolio.update_portfolio(date, target_portfolio, current_prices, safe_weight, current_gold_price, active_gold_ratio)
        
    return portfolio.get_equity_curve(), portfolio


def run_backtest():
    print("--- Starting Backtest Engine ---")
    
    # Load Configuration
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    barbell_cfg = cfg.get_barbell_strategy_params()
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
        print(f"ERROR: '{paths['symbols_file']}' not found.")
        return None

    # Initialize Components
    data_mgr = DataManager(
        universe, 
        start_date=bt_start, 
        end_date=bt_end, 
        cache_filename=paths['master_data_file'],
        live_mode=False
    )
    
    data_mgr.fetch_data()
    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    gold_prices = data_mgr.fetch_benchmark("GOLDBEES.NS")
    
    # Setup parameters
    momentum_params = {
        'portfolio_size': strat_cfg['portfolio_size'],
        'entry_rank': strat_cfg['entry_rank'],
        'exit_rank': strat_cfg['exit_rank'],
        'drawdown_limit': strat_cfg['drawdown_limit'],
        'momentum_lookback_days': strat_cfg['momentum_lookback_days'],
        'skip_latest_period': strat_cfg.get('skip_latest_period', False),
        'liquidate_on_bear_market': regime_cfg.get('liquidate_on_bear_market', False),
        'allocate_in_gold': regime_cfg.get('liquidate_on_bear_market', False),
        'gold_weight': 1.0,
        'regime_filter': regime_cfg.get('regime_filter', f"{regime_cfg.get('benchmark_dma_window', 200)}dma"),
        'use_adx_filter': regime_cfg.get('use_adx_filter', False),
        'adx_threshold': regime_cfg.get('adx_threshold', 20),
        'adx_window': regime_cfg.get('adx_window', 14),
        'rebalance_freq': cap_cfg.get('rebalance_frequency', 'W-FRI')
    }
    
    barbell_params = {
        'safe_weight_bull': barbell_cfg.get('safe_weight_bull', 0.30),
        'safe_weight_bear': barbell_cfg.get('safe_weight_bear', 0.80),
        'gold_ratio_in_safe': barbell_cfg.get('gold_ratio_in_safe', 0.50),
        'gold_trend_filter': barbell_cfg.get('gold_trend_filter', False),
        'gold_trend_lookback_days': barbell_cfg.get('gold_trend_lookback_days', 50),
        'risk_portfolio_size': barbell_cfg.get('risk_portfolio_size', 5),
        'entry_rank': barbell_cfg.get('entry_rank', 5),
        'exit_rank': barbell_cfg.get('exit_rank', 25),
        'drawdown_limit': barbell_cfg.get('drawdown_limit', 0.10),
        'momentum_lookback_days': barbell_cfg.get('momentum_lookback_days', 60),
        'skip_latest_period': barbell_cfg.get('skip_latest_period', False),
        'regime_filter': regime_cfg.get('regime_filter', f"{regime_cfg.get('benchmark_dma_window', 200)}dma"),
        'rebalance_freq': cap_cfg.get('rebalance_frequency', 'W-FRI')
    }
    
    initial_capital_per_slot = cap_cfg['allocation_per_slot']
    liquid_yield = cap_cfg.get('liquid_etf_yield', 0.0)
    rebalance_freq = momentum_params['rebalance_freq']
    
    initial_capital = initial_capital_per_slot * momentum_params['portfolio_size']
    
    print("\n--- Running Momentum Strategy Backtest ---")
    momentum_results_df, momentum_portfolio = run_single_backtest(
        params=momentum_params,
        data_mgr=data_mgr,
        bench_prices=bench_prices,
        gold_prices=gold_prices,
        bt_start=bt_start,
        bt_end=bt_end,
        initial_capital_per_slot=initial_capital_per_slot,
        liquid_yield=liquid_yield,
        rebalance_freq=rebalance_freq
    )
    
    print("\n--- Running Barbell Strategy Backtest ---")
    barbell_results_df, barbell_portfolio = run_single_barbell_backtest(
        params=barbell_params,
        data_mgr=data_mgr,
        bench_prices=bench_prices,
        gold_prices=gold_prices,
        bt_start=bt_start,
        bt_end=bt_end,
        initial_capital=initial_capital,
        liquid_yield=liquid_yield,
        rebalance_freq=rebalance_freq
    )
    
    print(f"\nMomentum Trades: {momentum_portfolio.total_trades} | Barbell Trades: {barbell_portfolio.total_trades}")
    print("\n--- Backtests Complete ---")
    
    # Save Journals
    momentum_journal_df = pd.DataFrame(momentum_portfolio.backtest_journal, columns=['Date', 'Action', 'Ticker', 'Shares', 'Price', 'Total Value'])
    momentum_journal_df.to_csv("backtest_trade_journal.csv", index=False)
    
    barbell_journal_df = pd.DataFrame(barbell_portfolio.backtest_journal, columns=['Date', 'Action', 'Ticker', 'Shares', 'Price', 'Total Value'])
    barbell_journal_df.to_csv("barbell_backtest_trade_journal.csv", index=False)
    
    # Save Results
    momentum_results_df.to_csv("backtest_results.csv")
    barbell_results_df.to_csv("barbell_backtest_results.csv")
    
    sliced_bench = None
    if bench_prices is not None and not bench_prices.empty:
        sliced_bench = bench_prices.loc[bt_start:bt_end].dropna()

    # Print Comparative Summary
    print_run_summary_comparison(
        momentum_df=momentum_results_df,
        momentum_trades=momentum_portfolio.total_trades,
        barbell_df=barbell_results_df,
        barbell_trades=barbell_portfolio.total_trades,
        initial_capital=initial_capital,
        start_date=bt_start,
        end_date=bt_end,
        bench_series=sliced_bench,
        bench_ticker=regime_cfg['benchmark_ticker']
    )

    # Append comparison entry to summary markdown
    append_comparison_to_markdown(
        momentum_df=momentum_results_df,
        momentum_portfolio=momentum_portfolio,
        momentum_params=momentum_params,
        barbell_df=barbell_results_df,
        barbell_portfolio=barbell_portfolio,
        barbell_params=barbell_params,
        start_date=bt_start,
        end_date=bt_end,
        bench_series=sliced_bench,
        bench_ticker=regime_cfg['benchmark_ticker']
    )

    return momentum_results_df, barbell_results_df


def append_comparison_to_markdown(momentum_df, momentum_portfolio, momentum_params, barbell_df, barbell_portfolio, barbell_params, start_date, end_date, bench_series=None, bench_ticker="Benchmark"):
    import os
    from datetime import datetime
    
    summary_file = "backtest_summary.md"
    file_exists = os.path.exists(summary_file)
    
    initial_capital = momentum_portfolio.initial_capital
    m_metrics = calculate_metrics(momentum_df['Total Equity'], initial_capital, start_date, end_date, bench_series)
    b_metrics = calculate_metrics(barbell_df['Total Equity'], initial_capital, start_date, end_date, bench_series)
    
    if bench_series is not None and not bench_series.empty:
        years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
        bench_start = bench_series.iloc[0]
        bench_end = bench_series.iloc[-1]
        bench_abs_return = ((bench_end - bench_start) / bench_start) * 100
        bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
        rolling_max_bench = bench_series.cummax()
        drawdown_bench = (bench_series - rolling_max_bench) / rolling_max_bench
        max_dd_bench = drawdown_bench.min() * 100
    else:
        bench_abs_return, bench_cagr, max_dd_bench = 0.0, 0.0, 0.0

    # Extract ledger trade analytics for Momentum
    m_ledger_df = convert_journal_to_ledger("backtest_trade_journal.csv")
    if not m_ledger_df.empty:
        m_analyzer = TradeAnalyzer(m_ledger_df)
        m_rep = m_analyzer.generate_report()
        m_win_rate = f"{m_rep['Win_Rate_Pct']}%"
        m_pf = f"{m_rep['Profit_Factor']}"
        m_payoff = f"{m_rep['Payoff_Ratio']}"
        m_win_loss = f"+{m_rep['Average_Win_Pct']}% / -{m_rep['Average_Loss_Pct']}%"
        m_days = f"{m_rep['Average_Days_Held']} days"
    else:
        m_win_rate = m_pf = m_payoff = m_win_loss = m_days = "N/A"

    # Extract ledger trade analytics for Barbell
    b_ledger_df = convert_journal_to_ledger("barbell_backtest_trade_journal.csv")
    if not b_ledger_df.empty:
        b_analyzer = TradeAnalyzer(b_ledger_df)
        b_rep = b_analyzer.generate_report()
        b_win_rate = f"{b_rep['Win_Rate_Pct']}%"
        b_pf = f"{b_rep['Profit_Factor']}"
        b_payoff = f"{b_rep['Payoff_Ratio']}"
        b_win_loss = f"+{b_rep['Average_Win_Pct']}% / -{b_rep['Average_Loss_Pct']}%"
        b_days = f"{b_rep['Average_Days_Held']} days"
    else:
        b_win_rate = b_pf = b_payoff = b_win_loss = b_days = "N/A"

    run_num = 1
    if file_exists:
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                content = f.read()
                run_num = content.count("## Run ") + 1
        except Exception:
            pass
            
    header = ""
    if not file_exists:
        header = "# Backtest Run History\n\nThis file tracks the rules, parameters, and performance results of each backtest execution.\n\n"

    entry = f"""{header}---

## Run {run_num}: Parallel Run (Momentum vs Barbell)
* **Execution Date**: {datetime.now().strftime('%Y-%m-%d')}
* **Momentum Setup**:
  * Entry: Top {momentum_params.get('entry_rank', 10)} by {momentum_params.get('momentum_lookback_days', 60)}-day ROC, close > {int((1-momentum_params.get('drawdown_limit', 0.10))*100)}% of rolling high.
  * Exit: Rank > {momentum_params.get('exit_rank', 50)} OR close $\le$ {int((1-momentum_params.get('drawdown_limit', 0.10))*100)}% of rolling high.
  * Regime Filter: Bullish if Benchmark > {momentum_params.get('regime_filter', '200dma')}. **Liquidate completely on Bear Market = {momentum_params.get('liquidate_on_bear_market', False)}**.
* **Barbell Setup**:
  * Safe Allocation: Bull = {barbell_params.get('safe_weight_bull', 0.30)*100:.0f}%, Bear = {barbell_params.get('safe_weight_bear', 0.80)*100:.0f}% (Split: {barbell_params.get('gold_ratio_in_safe', 0.50)*100:.0f}% Gold / {(1-barbell_params.get('gold_ratio_in_safe', 0.50))*100:.0f}% Cash).
  * Risk Allocation: Bull = {(1-barbell_params.get('safe_weight_bull', 0.30))*100:.0f}%, Bear = {(1-barbell_params.get('safe_weight_bear', 0.80))*100:.0f}% in {barbell_params.get('risk_portfolio_size', 5)} momentum slots.
  * Gold Trend Filter: {barbell_params.get('gold_trend_filter', False)} (Lookback: {barbell_params.get('gold_trend_lookback_days', 50)} days).
  * Entry: Top {barbell_params.get('entry_rank', 5)} by {barbell_params.get('momentum_lookback_days', 60)}-day ROC, close > {int((1-barbell_params.get('drawdown_limit', 0.10))*100)}% of rolling high.
  * Exit: Rank > {barbell_params.get('exit_rank', 25)} OR close $\le$ {int((1-barbell_params.get('drawdown_limit', 0.10))*100)}% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark ({bench_ticker}) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | {m_metrics['Abs Return %']:.2f}% | {b_metrics['Abs Return %']:.2f}% | {bench_abs_return:.2f}% |
| **CAGR** | {m_metrics['CAGR %']:.2f}% | {b_metrics['CAGR %']:.2f}% | {bench_cagr:.2f}% |
| **Max Drawdown** | {m_metrics['Max DD %']:.2f}% | {b_metrics['Max DD %']:.2f}% | {max_dd_bench:.2f}% |
| **Alpha (CAGR Diff)** | {m_metrics.get('Alpha %', 0.0):+.2f}% | {b_metrics.get('Alpha %', 0.0):+.2f}% | - |
| **Total Trades** | {momentum_portfolio.total_trades} | {barbell_portfolio.total_trades} | - |

### Trade Analytics
* **Win Rate**: Momentum = {m_win_rate} | Barbell = {b_win_rate}
* **Profit Factor**: Momentum = {m_pf} | Barbell = {b_pf}
* **Payoff Ratio**: Momentum = {m_payoff} | Barbell = {b_payoff}
* **Average Win / Loss**: Momentum = {m_win_loss} | Barbell = {b_win_loss}
* **Average Days Held**: Momentum = {m_days} | Barbell = {b_days}
"""
    
    with open(summary_file, 'a', encoding='utf-8') as f:
        f.write(entry + "\n")
    print(f"Run comparison results appended to {summary_file}")


if __name__ == "__main__":
    momentum_res, barbell_res = run_backtest()
    
    cfg = ConfigLoader('config.json')
    regime_cfg = cfg.get_regime_params()
    
    # Fetch benchmark data for plotting
    bt_cfg = cfg.get_backtest_params()
    bt_start = bt_cfg.get("start_date", "2016-01-01")
    bt_end = bt_cfg.get("end_date", "2026-01-01")
    
    # Reload benchmark for main run plotting
    symbols_df = pd.read_csv(cfg.get_paths()['symbols_file'])
    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
    data_mgr = DataManager(
        universe, 
        start_date=bt_start, 
        end_date=bt_end, 
        cache_filename=cfg.get_paths()['master_data_file'],
        live_mode=False
    )
    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
    sliced_bench = None
    if bench_prices is not None and not bench_prices.empty:
        sliced_bench = bench_prices.loc[bt_start:bt_end].dropna()

    plot_backtest_results(momentum_res, barbell_res, sliced_bench, regime_cfg['benchmark_ticker'])
