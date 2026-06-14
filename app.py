import os
import pandas as pd
import math
from datetime import datetime, timedelta
import streamlit as st
import yfinance as yf

# Import your shared brain
from core import DataManager, MomentumStrategy, ConfigLoader
from analytics import calculate_metrics, convert_journal_to_ledger, TradeAnalyzer

# --- PAGE CONFIGURATION & CSS COMPRESSION ---
st.set_page_config(page_title="Quant Command Center", page_icon="⚙️", layout="wide")

# Premium CSS Styling
st.markdown("""
    <style>
        /* 1. Completely hide the default Streamlit banner/header */
        [data-testid="stHeader"] {
            display: none !important;
        }
        
        /* 2. Adjust the main container to sit perfectly at the top edge */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 1rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        
        /* 3. Make the dataframe UI tighter */
        [data-testid="stDataFrame"] { 
            margin-bottom: 0px; 
        }

        /* 4. Beautiful custom tabs and buttons */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            gap: 8px;
            padding-top: 10px;
            padding-bottom: 10px;
            font-weight: 600;
            font-size: 16px;
        }
    </style>
    """, unsafe_allow_html=True)

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

def append_to_journal(trades, filepath='trading_journal.csv'):
    if not trades: return
    df = pd.DataFrame(trades)
    if not os.path.exists(filepath):
        df.to_csv(filepath, index=False)
    else:
        df.to_csv(filepath, mode='a', header=False, index=False)

# ==========================================
# UI STATE NAMESPACE INITIALIZATION
# ==========================================
state_keys = [
    'signals_generated', 'proposed_sells', 'proposed_buys', 'proposed_holds',
    'new_positions', 'executed_trades', 'top_leaders', 'live_equity', 'live_cash',
    'curr_roc', 'is_bull_market', 'latest_price_date'
]

# Prefix: 'm_' for Momentum, 'b_' for Barbell
for prefix in ['m_', 'b_']:
    for key in state_keys:
        state_key = prefix + key
        if state_key not in st.session_state:
            if 'generated' in key or 'market' in key:
                st.session_state[state_key] = False
            elif 'leaders' in key:
                st.session_state[state_key] = pd.DataFrame()
            elif 'proposed' in key or 'trades' in key:
                st.session_state[state_key] = []
            elif 'positions' in key:
                st.session_state[state_key] = {}
            elif 'equity' in key or 'cash' in key or 'roc' in key:
                st.session_state[state_key] = 0.0
            else:
                st.session_state[state_key] = None

# ==========================================
# CORE DASHBOARD
# ==========================================
def main():
    run_date = datetime.now().strftime('%Y-%m-%d | %H:%M')
    
    # 1. LOAD CONFIGURATION & STATE
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    barbell_cfg = cfg.get_barbell_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()

    st.markdown(f"## ⚙️ Quant Command Center <span style='font-size:14px;color:gray;float:right;margin-top:12px;'>Last Updated: {run_date}</span>", unsafe_allow_html=True)
    st.markdown("---")

    # Sidebar parameters
    st.sidebar.header("Capital Allocation")
    user_cash_m = st.sidebar.number_input(
        "Momentum Cash (₹)", 
        value=float(cap_cfg.get('allocation_per_slot', 25000) * strat_cfg['portfolio_size']), 
        step=5000.0,
        help="Uninvested cash allocated to the Momentum Strategy."
    )
    
    user_cash_b = st.sidebar.number_input(
        "Barbell Cash (₹)", 
        value=float(cap_cfg.get('allocation_per_slot', 25000) * barbell_cfg.get('risk_portfolio_size', 5) * 2), 
        step=5000.0,
        help="Uninvested cash allocated to the Barbell Strategy."
    )

    # Tabs for strategies
    tab1, tab2, tab3 = st.tabs(["🚀 Momentum Strategy", "⚖️ Barbell Strategy", "📊 Strategy Comparison"])

    # ----------------------------------------------------
    # TAB 1: MOMENTUM STRATEGY
    # ----------------------------------------------------
    with tab1:
        col_t, col_s, col_b = st.columns([3, 4, 2], vertical_alignment="bottom")
        current_positions_m = load_current_positions(paths.get('holdings_file', 'current_holdings.csv'))
        
        with col_t:
            st.subheader("Momentum Live Operations")
        with col_s:
            if st.session_state.m_live_equity > 0:
                m1, m2, m3 = st.columns(3)
                m1.metric("Live Equity", f"₹{st.session_state.m_live_equity:,.0f}")
                m2.metric("Uninvested Cash", f"₹{st.session_state.m_live_cash:,.0f}")
                m3.metric("Positions", len(current_positions_m))
        with col_b:
            if st.button("🔥 Run Momentum Analysis", use_container_width=True, type="primary"):
                with st.spinner("Generating momentum signals..."):
                    symbols_df = pd.read_csv(paths['symbols_file'])
                    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
                    
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
                    
                    data_mgr = DataManager(universe, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), live_mode=True)
                    prices = data_mgr.fetch_data()
                    momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
                    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])
                    
                    rebalance_freq = cap_cfg.get('rebalance_frequency', 'W-FRI')
                    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
                    latest_prices = prices.iloc[-1]
                    
                    # Sizing Math
                    pos_value = sum(current_positions_m[t] * latest_prices.get(t, 0) for t in current_positions_m)
                    total_live_equity = pos_value + user_cash_m
                    st.session_state.m_live_equity = total_live_equity
                    st.session_state.m_live_cash = user_cash_m
                    
                    dynamic_allocation_per_slot = total_live_equity / strat_cfg['portfolio_size']
                    
                    weekly_bench_prices = bench_prices.resample(rebalance_freq).last().dropna()
                    if len(weekly_bench_prices) >= 2:
                        curr_roc = (weekly_bench_prices.iloc[-1] / weekly_bench_prices.iloc[-2]) - 1
                        st.session_state.m_curr_roc = curr_roc
                    else:
                        st.session_state.m_curr_roc = 0.0
                    
                    # Lag check
                    if strat_cfg.get('skip_latest_period', False):
                        resampled_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
                        if len(resampled_momentum) >= 2:
                            latest_momentum = resampled_momentum.iloc[-2]
                        else:
                            latest_momentum = momentum_df.iloc[-1]
                    else:
                        latest_momentum = momentum_df.iloc[-1]
                        
                    latest_highs = rolling_highs_df.iloc[-1]
                    
                    affordable_tickers = latest_prices[latest_prices <= dynamic_allocation_per_slot].index
                    latest_momentum = latest_momentum.reindex(affordable_tickers).dropna()
                    
                    # Market Regime
                    try:
                        bench_dma = bench_prices.rolling(window=regime_cfg.get('benchmark_dma_window', 200)).mean()
                        is_bull_market = bench_prices.iloc[-1] > bench_dma.iloc[-1]
                    except:
                        is_bull_market = True
                    
                    st.session_state.m_is_bull_market = is_bull_market
                    
                    # Strategy instance
                    strategy = MomentumStrategy(
                        portfolio_size=strat_cfg['portfolio_size'], entry_rank=strat_cfg['entry_rank'],
                        exit_rank=strat_cfg['exit_rank'], drawdown_limit=strat_cfg['drawdown_limit']
                    )
                    
                    # Leaderboard
                    latest_price_date = prices.index[-1].strftime('%Y-%m-%d')
                    st.session_state.m_latest_price_date = latest_price_date
                    
                    drawdown_mask = latest_prices > (latest_highs * (1 - strategy.drawdown_limit))
                    qualified_momentum = latest_momentum[drawdown_mask].sort_values(ascending=False)
                    top_leaders = qualified_momentum.head(strategy.exit_rank).reset_index()
                    top_leaders.columns = ['Ticker', 'Momentum Score']
                    top_leaders['Rank'] = top_leaders.index + 1
                    top_leaders['Price'] = top_leaders['Ticker'].apply(lambda x: latest_prices.get(x, 0))
                    
                    st.session_state.m_top_leaders = top_leaders[['Rank', 'Ticker', 'Momentum Score', 'Price']]
                    
                    # Target list
                    current_tickers = list(current_positions_m.keys())
                    target_portfolio = strategy.get_target_portfolio(latest_momentum, current_tickers, latest_prices, latest_highs, market_bullish=is_bull_market)
                    
                    # Reconcile Delta
                    sells = [t for t in current_tickers if t not in target_portfolio]
                    buys = [t for t in target_portfolio if t not in current_tickers]
                    holds = [t for t in current_tickers if t in target_portfolio]
                    
                    proposed_sells, proposed_buys, proposed_holds = [], [], []
                    
                    for ticker in sells:
                        shares = current_positions_m[ticker]
                        price = latest_prices.get(ticker, 0)
                        proposed_sells.append({"Ticker": ticker, "Action": "SELL", "Shares": int(shares), "Execution Price": round(float(price), 2)})
                        
                    for ticker in buys:
                        price = latest_prices.get(ticker, 0)
                        if pd.notna(price) and price > 0:
                            shares = math.floor(dynamic_allocation_per_slot / price)
                            cost = shares * price
                            proposed_buys.append({"Ticker": ticker, "Action": "BUY", "Shares": int(shares), "Execution Price": round(float(price), 2), "Total Amount": round(float(cost), 2)})
                            
                    for ticker in holds:
                        shares = current_positions_m[ticker]
                        proposed_holds.append({"Ticker": ticker, "Shares": int(shares)})
                        
                    st.session_state.m_signals_generated = True
                    st.session_state.m_proposed_sells = proposed_sells
                    st.session_state.m_proposed_buys = proposed_buys
                    st.session_state.m_proposed_holds = proposed_holds

        st.markdown("---")

        if st.session_state.m_signals_generated:
            if st.session_state.m_is_bull_market:
                st.success(f"🟢 **BULLISH REGIME** | Benchmark > 200DMA | Nifty 500 ROC: {st.session_state.m_curr_roc * 100:.2f}% | Deploying fully.", icon="✅")
            else:
                st.warning(f"🔴 **BEARISH REGIME** | Benchmark < 200DMA | Nifty 500 ROC: {st.session_state.m_curr_roc * 100:.2f}% | New momentum entries blocked.", icon="⚠️")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**📉 Sells Required ({len(st.session_state.m_proposed_sells)})**")
                if st.session_state.m_proposed_sells:
                    edited_sells = st.data_editor(pd.DataFrame(st.session_state.m_proposed_sells), hide_index=True, use_container_width=True, key="m_sells_editor")
                else:
                    st.info("No Momentum liquidations needed.")
                    edited_sells = pd.DataFrame()
            with col2:
                st.markdown(f"**📈 Buys Required ({len(st.session_state.m_proposed_buys)})**")
                if st.session_state.m_proposed_buys:
                    edited_buys = st.data_editor(pd.DataFrame(st.session_state.m_proposed_buys), hide_index=True, use_container_width=True, key="m_buys_editor")
                else:
                    st.info("No Momentum purchases needed.")
                    edited_buys = pd.DataFrame()

            with st.expander(f"🔵 Active Holds Maintained ({len(st.session_state.m_proposed_holds)})"):
                if st.session_state.m_proposed_holds:
                    st.dataframe(pd.DataFrame(st.session_state.m_proposed_holds), hide_index=True, use_container_width=True)
                else:
                    st.write("No active Momentum holds.")

            if not st.session_state.m_top_leaders.empty:
                with st.expander(f"🏆 Top Momentum Leaders (Prices as of {st.session_state.m_latest_price_date})"):
                    st.dataframe(st.session_state.m_top_leaders, hide_index=True, use_container_width=True)

            if st.session_state.m_proposed_buys or st.session_state.m_proposed_sells:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Confirm Momentum Execution", type="primary", use_container_width=True):
                    final_positions = {}
                    final_trades = []
                    
                    for h in st.session_state.m_proposed_holds:
                        final_positions[h['Ticker']] = h['Shares']
                        
                    if not edited_sells.empty:
                        for _, row in edited_sells.iterrows():
                            final_trades.append({
                                'Date': run_date, 'Action': 'SELL', 'Ticker': row['Ticker'],
                                'Shares': row['Shares'], 'Execution_Price': row['Execution Price'],
                                'Total_Amount': round(row['Shares'] * row['Execution Price'], 2)
                            })
                            
                    if not edited_buys.empty:
                        for _, row in edited_buys.iterrows():
                            final_trades.append({
                                'Date': run_date, 'Action': 'BUY', 'Ticker': row['Ticker'],
                                'Shares': row['Shares'], 'Execution_Price': row['Execution Price'],
                                'Total_Amount': round(row['Shares'] * row['Execution Price'], 2)
                            })
                            final_positions[row['Ticker']] = row['Shares']
                            
                    save_new_positions(final_positions, paths.get('holdings_file', 'current_holdings.csv'))
                    append_to_journal(final_trades, paths.get('journal_file', 'trading_journal.csv'))
                    st.success("Momentum Ledgers updated successfully!")
                    st.balloons()
                    st.session_state.m_signals_generated = False
            else:
                st.success("Momentum Portfolio is fully synced.")


    # ----------------------------------------------------
    # TAB 2: BARBELL STRATEGY
    # ----------------------------------------------------
    with tab2:
        col_t, col_s, col_b = st.columns([3, 4, 2], vertical_alignment="bottom")
        barbell_holdings_file = paths.get('barbell_holdings_file', 'barbell_holdings.csv')
        current_positions_b = load_current_positions(barbell_holdings_file)
        
        with col_t:
            st.subheader("Barbell Live Operations")
        with col_s:
            if st.session_state.b_live_equity > 0:
                m1, m2, m3 = st.columns(3)
                m1.metric("Live Equity", f"₹{st.session_state.b_live_equity:,.0f}")
                m2.metric("Uninvested Cash", f"₹{st.session_state.b_live_cash:,.0f}")
                m3.metric("Positions", len(current_positions_b))
        with col_b:
            if st.button("⚖️ Run Barbell Analysis", use_container_width=True, type="primary"):
                with st.spinner("Generating barbell signals..."):
                    symbols_df = pd.read_csv(paths['symbols_file'])
                    universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
                    
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
                    
                    # Fetch Stock data
                    data_mgr = DataManager(universe, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), live_mode=True)
                    prices = data_mgr.fetch_data()
                    momentum_df = data_mgr.calculate_momentum(lookback_days=barbell_cfg.get('momentum_lookback_days', 60))
                    rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=barbell_cfg.get('momentum_lookback_days', 60))
                    
                    rebalance_freq = cap_cfg.get('rebalance_frequency', 'W-FRI')
                    bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
                    latest_prices = prices.iloc[-1]
                    
                    # Fetch Gold price and calculate trend
                    is_gold_bullish = True
                    try:
                        gold_df = yf.download("GOLDBEES.NS", period="1y", progress=False)
                        col = 'Adj Close' if 'Adj Close' in gold_df.columns else 'Close'
                        if isinstance(gold_df.columns, pd.MultiIndex):
                            gold_series = gold_df[col].iloc[:, 0]
                        else:
                            gold_series = gold_df[col]
                        latest_gold_price = float(gold_series.iloc[-1])
                        
                        gold_trend_filter = barbell_cfg.get('gold_trend_filter', False)
                        gold_trend_lookback = barbell_cfg.get('gold_trend_lookback_days', 50)
                        if gold_trend_filter:
                            gold_ma = gold_series.rolling(window=gold_trend_lookback).mean()
                            is_gold_bullish = latest_gold_price > gold_ma.iloc[-1]
                    except Exception:
                        latest_gold_price = 70.0
                        is_gold_bullish = True
                        
                    st.session_state.b_is_gold_bullish = is_gold_bullish
                        
                    # Market Regime Check
                    try:
                        bench_dma = bench_prices.rolling(window=regime_cfg.get('benchmark_dma_window', 200)).mean()
                        is_bull_market = bench_prices.iloc[-1] > bench_dma.iloc[-1]
                    except:
                        is_bull_market = True
                        
                    st.session_state.b_is_bull_market = is_bull_market
                    
                    weekly_bench_prices = bench_prices.resample(rebalance_freq).last().dropna()
                    if len(weekly_bench_prices) >= 2:
                        st.session_state.b_curr_roc = (weekly_bench_prices.iloc[-1] / weekly_bench_prices.iloc[-2]) - 1
                    else:
                        st.session_state.b_curr_roc = 0.0

                    # Sizing Math
                    stock_value = sum(current_positions_b[t] * latest_prices.get(t, 0) for t in current_positions_b if t != 'GOLDBEES.NS')
                    gold_shares = current_positions_b.get('GOLDBEES.NS', 0)
                    gold_value = gold_shares * latest_gold_price
                    total_positions_value = stock_value + gold_value
                    
                    total_live_equity = total_positions_value + user_cash_b
                    
                    st.session_state.b_live_equity = total_live_equity
                    st.session_state.b_live_cash = user_cash_b
                    
                    # Dynamic Barbell allocations
                    safe_weight_bull = barbell_cfg.get('safe_weight_bull', 0.30)
                    safe_weight_bear = barbell_cfg.get('safe_weight_bear', 0.80)
                    safe_weight = safe_weight_bull if is_bull_market else safe_weight_bear
                    st.session_state.b_safe_weight = safe_weight
                    
                    gold_ratio_cfg = barbell_cfg.get('gold_ratio_in_safe', 0.50)
                    active_gold_ratio = gold_ratio_cfg if is_gold_bullish else 0.0
                    st.session_state.b_active_gold_ratio = active_gold_ratio
                    
                    risk_slots = barbell_cfg.get('risk_portfolio_size', 5)
                    
                    target_safe_value = total_live_equity * safe_weight
                    target_risk_value = total_live_equity * (1 - safe_weight)
                    target_gold_value = target_safe_value * active_gold_ratio
                    target_gold_shares = math.floor(target_gold_value / latest_gold_price) if latest_gold_price > 0 else 0
                    
                    dynamic_allocation_per_slot = target_risk_value / risk_slots
                    
                    # Lag check
                    if barbell_cfg.get('skip_latest_period', False):
                        resampled_momentum = momentum_df.resample(rebalance_freq).last().dropna(how='all')
                        if len(resampled_momentum) >= 2:
                            latest_momentum = resampled_momentum.iloc[-2]
                        else:
                            latest_momentum = momentum_df.iloc[-1]
                    else:
                        latest_momentum = momentum_df.iloc[-1]
                        
                    latest_highs = rolling_highs_df.iloc[-1]
                    
                    affordable_tickers = latest_prices[latest_prices <= dynamic_allocation_per_slot].index
                    latest_momentum = latest_momentum.reindex(affordable_tickers).dropna()
                    
                    # Barbell Strategy uses MomentumStrategy block but with risk parameters
                    strategy = MomentumStrategy(
                        portfolio_size=risk_slots, 
                        entry_rank=barbell_cfg.get('entry_rank', 5),
                        exit_rank=barbell_cfg.get('exit_rank', 25), 
                        drawdown_limit=barbell_cfg.get('drawdown_limit', 0.10)
                    )
                    
                    latest_price_date = prices.index[-1].strftime('%Y-%m-%d')
                    st.session_state.b_latest_price_date = latest_price_date
                    st.session_state.b_latest_gold_price = latest_gold_price
                    st.session_state.b_target_gold_shares = target_gold_shares
                    st.session_state.b_gold_shares = gold_shares
                    
                    drawdown_mask = latest_prices > (latest_highs * (1 - strategy.drawdown_limit))
                    qualified_momentum = latest_momentum[drawdown_mask].sort_values(ascending=False)
                    top_leaders = qualified_momentum.head(strategy.exit_rank).reset_index()
                    top_leaders.columns = ['Ticker', 'Momentum Score']
                    top_leaders['Rank'] = top_leaders.index + 1
                    top_leaders['Price'] = top_leaders['Ticker'].apply(lambda x: latest_prices.get(x, 0))
                    
                    st.session_state.b_top_leaders = top_leaders[['Rank', 'Ticker', 'Momentum Score', 'Price']]
                    
                    # Target risk stocks
                    current_tickers = [t for t in current_positions_b.keys() if t != 'GOLDBEES.NS']
                    # Barbell ignores the regime filter
                    target_portfolio = strategy.get_target_portfolio(latest_momentum, current_tickers, latest_prices, latest_highs, market_bullish=True)
                    
                    # Reconcile Delta
                    sells = [t for t in current_tickers if t not in target_portfolio]
                    buys = [t for t in target_portfolio if t not in current_tickers]
                    holds = [t for t in current_tickers if t in target_portfolio]
                    
                    proposed_sells, proposed_buys, proposed_holds = [], [], []
                    
                    # Sells (Stocks)
                    for ticker in sells:
                        shares = current_positions_b[ticker]
                        price = latest_prices.get(ticker, 0)
                        proposed_sells.append({"Ticker": ticker, "Action": "SELL", "Shares": int(shares), "Execution Price": round(float(price), 2)})
                        
                    # Sell Gold
                    gold_diff = target_gold_shares - gold_shares
                    if gold_diff < 0:
                        proposed_sells.append({"Ticker": "GOLDBEES.NS", "Action": "SELL", "Shares": int(abs(gold_diff)), "Execution Price": round(latest_gold_price, 2)})
                        
                    # Buys (Stocks)
                    for ticker in buys:
                        price = latest_prices.get(ticker, 0)
                        if pd.notna(price) and price > 0:
                            shares = math.floor(dynamic_allocation_per_slot / price)
                            cost = shares * price
                            proposed_buys.append({"Ticker": ticker, "Action": "BUY", "Shares": int(shares), "Execution Price": round(float(price), 2), "Total Amount": round(float(cost), 2)})
                            
                    # Buy Gold
                    if gold_diff > 0:
                        cost = gold_diff * latest_gold_price
                        proposed_buys.append({"Ticker": "GOLDBEES.NS", "Action": "BUY", "Shares": int(gold_diff), "Execution Price": round(latest_gold_price, 2), "Total Amount": round(float(cost), 2)})
                        
                    # Holds (Stocks)
                    for ticker in holds:
                        shares = current_positions_b[ticker]
                        proposed_holds.append({"Ticker": ticker, "Shares": int(shares)})
                        
                    if gold_shares > 0 and gold_diff == 0:
                        proposed_holds.append({"Ticker": "GOLDBEES.NS", "Shares": int(gold_shares)})
                        
                    st.session_state.b_signals_generated = True
                    st.session_state.b_proposed_sells = proposed_sells
                    st.session_state.b_proposed_buys = proposed_buys
                    st.session_state.b_proposed_holds = proposed_holds

        st.markdown("---")

        if st.session_state.b_signals_generated:
            col_reg1, col_reg2 = st.columns(2)
            with col_reg1:
                if st.session_state.b_is_bull_market:
                    st.success(f"🟢 **MARKET REGIME: BULLISH** (Benchmark > 200DMA)\nNifty 500 ROC: {st.session_state.b_curr_roc * 100:.2f}%\nAllocation: **70% Risk / 30% Safe** split.", icon="✅")
                else:
                    st.warning(f"🔴 **MARKET REGIME: BEARISH** (Benchmark < 200DMA)\nNifty 500 ROC: {st.session_state.b_curr_roc * 100:.2f}%\nAllocation: **20% Risk / 80% Safe** split.", icon="⚠️")
            with col_reg2:
                is_gold_bullish = st.session_state.get('b_is_gold_bullish', True)
                gold_trend_lookback = barbell_cfg.get('gold_trend_lookback_days', 50)
                if is_gold_bullish:
                    st.success(f"✨ **GOLD REGIME: BULLISH** (Price > {gold_trend_lookback}DMA)\nTrend: Upward\nAllocation: **Safe split at config settings**.", icon="📈")
                else:
                    st.warning(f"✨ **GOLD REGIME: BEARISH** (Price <= {gold_trend_lookback}DMA)\nTrend: Downward\nAllocation: **100% of safe assets to Yield Cash**.", icon="📉")

            # Barbell Header
            active_safe_weight = st.session_state.get('b_safe_weight', 0.50)
            active_gold_ratio = st.session_state.get('b_active_gold_ratio', 0.50)
            safe_pct = active_safe_weight * 100
            risk_pct = (1 - active_safe_weight) * 100
            gold_ratio_pct = active_gold_ratio * 100
            cash_ratio_pct = (1 - active_gold_ratio) * 100
            
            st.info(f"⚖️ **BARBELL BALANCE**: Safe Leg {safe_pct:.0f}% ({gold_ratio_pct:.0f}% Gold ETF / {cash_ratio_pct:.0f}% Yield Cash) | Risk Leg {risk_pct:.0f}% (Top {barbell_cfg.get('risk_portfolio_size', 5)} Momentum Slots)", icon="⚖️")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**📉 Sells Required ({len(st.session_state.b_proposed_sells)})**")
                if st.session_state.b_proposed_sells:
                    edited_sells_b = st.data_editor(pd.DataFrame(st.session_state.b_proposed_sells), hide_index=True, use_container_width=True, key="b_sells_editor")
                else:
                    st.info("No Barbell liquidations needed.")
                    edited_sells_b = pd.DataFrame()
            with col2:
                st.markdown(f"**📈 Buys Required ({len(st.session_state.b_proposed_buys)})**")
                if st.session_state.b_proposed_buys:
                    edited_buys_b = st.data_editor(pd.DataFrame(st.session_state.b_proposed_buys), hide_index=True, use_container_width=True, key="b_buys_editor")
                else:
                    st.info("No Barbell purchases needed.")
                    edited_buys_b = pd.DataFrame()

            with st.expander(f"🔵 Active Holds Maintained ({len(st.session_state.b_proposed_holds)})"):
                if st.session_state.b_proposed_holds:
                    st.dataframe(pd.DataFrame(st.session_state.b_proposed_holds), hide_index=True, use_container_width=True)
                else:
                    st.write("No active Barbell holds.")

            if not st.session_state.b_top_leaders.empty:
                with st.expander(f"🏆 Top Barbell Momentum Pool (Prices as of {st.session_state.b_latest_price_date})"):
                    st.dataframe(st.session_state.b_top_leaders, hide_index=True, use_container_width=True)

            if st.session_state.b_proposed_buys or st.session_state.b_proposed_sells:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Confirm Barbell Execution", type="primary", use_container_width=True):
                    final_positions_b = {}
                    final_trades_b = []
                    
                    # Start with holds
                    for h in st.session_state.b_proposed_holds:
                        final_positions_b[h['Ticker']] = h['Shares']
                        
                    # Sells confirm
                    if not edited_sells_b.empty:
                        for _, row in edited_sells_b.iterrows():
                            final_trades_b.append({
                                'Date': run_date, 'Action': 'SELL', 'Ticker': row['Ticker'],
                                'Shares': row['Shares'], 'Execution_Price': row['Execution Price'],
                                'Total_Amount': round(row['Shares'] * row['Execution Price'], 2)
                            })
                            if row['Ticker'] == 'GOLDBEES.NS':
                                new_gold_shares = st.session_state.b_gold_shares - row['Shares']
                                if new_gold_shares > 0:
                                    final_positions_b['GOLDBEES.NS'] = new_gold_shares
                            # Non-gold stocks are completely liquidated
                            
                    # Buys confirm
                    if not edited_buys_b.empty:
                        for _, row in edited_buys_b.iterrows():
                            final_trades_b.append({
                                'Date': run_date, 'Action': 'BUY', 'Ticker': row['Ticker'],
                                'Shares': row['Shares'], 'Execution_Price': row['Execution Price'],
                                'Total_Amount': round(row['Shares'] * row['Execution Price'], 2)
                            })
                            if row['Ticker'] == 'GOLDBEES.NS':
                                final_positions_b['GOLDBEES.NS'] = st.session_state.b_gold_shares + row['Shares']
                            else:
                                final_positions_b[row['Ticker']] = row['Shares']
                                
                    save_new_positions(final_positions_b, barbell_holdings_file)
                    append_to_journal(final_trades_b, paths.get('barbell_journal_file', 'barbell_trading_journal.csv'))
                    st.success("Barbell Ledgers updated successfully!")
                    st.balloons()
                    st.session_state.b_signals_generated = False
            else:
                st.success("Barbell Portfolio is fully synced.")


    # ----------------------------------------------------
    # TAB 3: STRATEGY COMPARISON
    # ----------------------------------------------------
    with tab3:
        st.subheader("Historical Backtest Comparison")
        st.write("Compare the performance of the pure Momentum Strategy versus the Barbell Strategy side-by-side.")
        
        col_btn_run, _ = st.columns([2, 8])
        with col_btn_run:
            if st.button("🚀 Run Comparative Backtest", use_container_width=True, type="primary"):
                with st.spinner("Running historical backtests for both strategies (10 Year Horizon)..."):
                    try:
                        from backtest import run_backtest
                        # Execute the parallel engine
                        run_backtest()
                        st.success("Backtest simulation completed and updated!")
                    except Exception as e:
                        st.error(f"Failed to execute backtest: {e}")
                        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if os.path.exists("backtest_results.csv") and os.path.exists("barbell_backtest_results.csv"):
            # Load historical equity curves
            m_res = pd.read_csv("backtest_results.csv", index_col=0, parse_dates=True)
            b_res = pd.read_csv("barbell_backtest_results.csv", index_col=0, parse_dates=True)
            
            # 1. Plot Equity Curve Comparison
            comparison_df = pd.DataFrame({
                "Momentum Strategy": m_res["Total Equity"],
                "Barbell Strategy": b_res["Total Equity"]
            })
            st.markdown("### Total Equity Growth Comparison (INR)")
            st.line_chart(comparison_df, use_container_width=True)
            
            # 2. Compute Metrics Side-by-Side
            initial_cap = m_res["Total Equity"].iloc[0]
            start_date_str = m_res.index[0].strftime('%Y-%m-%d')
            end_date_str = m_res.index[-1].strftime('%Y-%m-%d')
            
            # Benchmark series loader
            sliced_bench = None
            try:
                # Reload cache and benchmark ticker to calculate exact metrics
                master_df = pd.read_parquet(paths['master_data_file'])
                master_df.index = pd.to_datetime(master_df.index)
                sliced_bench = master_df[regime_cfg['benchmark_ticker']].loc[m_res.index[0]:m_res.index[-1]].dropna()
            except Exception:
                pass
                
            m_metrics = calculate_metrics(m_res['Total Equity'], initial_cap, start_date_str, end_date_str, sliced_bench)
            b_metrics = calculate_metrics(b_res['Total Equity'], initial_cap, start_date_str, end_date_str, sliced_bench)
            
            if sliced_bench is not None and not sliced_bench.empty:
                years = (pd.to_datetime(end_date_str) - pd.to_datetime(start_date_str)).days / 365.25
                bench_start = sliced_bench.iloc[0]
                bench_end = sliced_bench.iloc[-1]
                bench_abs = ((bench_end - bench_start) / bench_start) * 100
                bench_cagr = ((bench_end / bench_start) ** (1 / years) - 1) * 100 if years > 0 else 0.0
                rolling_max_bench = sliced_bench.cummax()
                drawdown_bench = (sliced_bench - rolling_max_bench) / rolling_max_bench
                bench_max_dd = drawdown_bench.min() * 100
            else:
                bench_abs = bench_cagr = bench_max_dd = 0.0
                
            # Trade counts
            m_trade_count = 0
            if os.path.exists("backtest_trade_journal.csv"):
                m_trade_count = len(pd.read_csv("backtest_trade_journal.csv"))
            b_trade_count = 0
            if os.path.exists("barbell_backtest_trade_journal.csv"):
                b_trade_count = len(pd.read_csv("barbell_backtest_trade_journal.csv"))
                
            # Display metrics cards
            st.markdown("### Performance Comparison Dashboard")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("<div style='background-color:rgba(31, 119, 180, 0.1);padding:15px;border-radius:5px;'>", unsafe_allow_html=True)
                st.subheader("🚀 Momentum Strategy")
                st.metric("Absolute Return", f"{m_metrics['Abs Return %']:.2f}%")
                st.metric("CAGR", f"{m_metrics['CAGR %']:.2f}%")
                st.metric("Max Drawdown", f"{m_metrics['Max DD %']:.2f}%")
                st.metric("Alpha (CAGR vs Bench)", f"{m_metrics.get('Alpha %', 0.0):+.2f}%")
                st.metric("Total Trades", f"{m_trade_count}")
                st.markdown("</div>", unsafe_allow_html=True)
                
            with c2:
                st.markdown("<div style='background-color:rgba(44, 160, 44, 0.1);padding:15px;border-radius:5px;'>", unsafe_allow_html=True)
                st.subheader("⚖️ Barbell Strategy")
                st.metric("Absolute Return", f"{b_metrics['Abs Return %']:.2f}%")
                st.metric("CAGR", f"{b_metrics['CAGR %']:.2f}%")
                st.metric("Max Drawdown", f"{b_metrics['Max DD %']:.2f}%")
                st.metric("Alpha (CAGR vs Bench)", f"{b_metrics.get('Alpha %', 0.0):+.2f}%")
                st.metric("Total Trades", f"{b_trade_count}")
                st.markdown("</div>", unsafe_allow_html=True)
                
            with c3:
                st.markdown("<div style='background-color:rgba(255, 127, 14, 0.1);padding:15px;border-radius:5px;'>", unsafe_allow_html=True)
                st.subheader(f"📈 Benchmark ({regime_cfg['benchmark_ticker']})")
                st.metric("Absolute Return", f"{bench_abs:.2f}%")
                st.metric("CAGR", f"{bench_cagr:.2f}%")
                st.metric("Max Drawdown", f"{bench_max_dd:.2f}%")
                st.metric("Alpha", "0.00%")
                st.metric("Total Trades", "-")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("⚠️ No backtest simulation logs found. Click 'Run Comparative Backtest' above to generate and view the comparison metrics.")

if __name__ == "__main__":
    main()
