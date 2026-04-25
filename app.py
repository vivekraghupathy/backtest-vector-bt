import os
import pandas as pd
import math
from datetime import datetime, timedelta
import streamlit as st

# Import your shared brain
from core import DataManager, MomentumStrategy, ConfigLoader

# --- PAGE CONFIGURATION & CSS COMPRESSION ---
st.set_page_config(page_title="Quant Command", page_icon="⚙️", layout="wide")

# This CSS completely hides the Streamlit header and perfectly spaces the HUD
st.markdown("""
    <style>
        /* 1. Completely hide the default Streamlit banner/header */
        [data-testid="stHeader"] {
            display: none !important;
        }
        
        /* 2. Adjust the main container to sit perfectly at the top edge */
        .block-container {
            padding-top: 2rem !important; /* Slightly increased to prevent edge-clipping */
            padding-bottom: 1rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        
        /* 3. Make the dataframe UI tighter */
        [data-testid="stDataFrame"] { 
            margin-bottom: 0px; 
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
# UI STATE MANAGEMENT
# ==========================================
if 'signals_generated' not in st.session_state:
    st.session_state.signals_generated = False
if 'proposed_sells' not in st.session_state:
    st.session_state.proposed_sells = []
if 'proposed_buys' not in st.session_state:
    st.session_state.proposed_buys = []
if 'proposed_holds' not in st.session_state:
    st.session_state.proposed_holds = []
if 'new_positions' not in st.session_state:
    st.session_state.new_positions = {}
if 'executed_trades' not in st.session_state:
    st.session_state.executed_trades = []

# ==========================================
# CORE DASHBOARD
# ==========================================
def main():
    run_date = datetime.now().strftime('%Y-%m-%d | %H:%M')
    
    # 1. LOAD CONFIGURATION & STATE
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    allocation_per_slot = cap_cfg.get('allocation_per_slot', 25000)

    current_positions = load_current_positions(paths.get('holdings_file', 'current_holdings.csv'))
    
    # --- THE HUD (Heads-Up Display) ---
    # Compresses Title, Date, Live State, and Generate Button into one horizontal block
    col_title, col_state, col_btn = st.columns([2, 3, 1], vertical_alignment="bottom")
    
    with col_title:
        st.markdown(f"### Momentum Engine<br><small style='color:gray;'>{run_date}</small>", unsafe_allow_html=True)
        
    # with col_state:
    #     # We read the validation ledger to populate the live HUD metrics
    #     try:
    #         live_df = pd.read_csv("backtest_validation_ledger.csv")
    #         latest = live_df.iloc[-1]
    #         m1, m2, m3 = st.columns(3)
    #         m1.metric("Live Equity", f"₹{latest['Total Equity']:,.0f}")
    #         m2.metric("Cash", f"₹{latest['Cash']:,.0f}")
    #         m3.metric("Positions", int(latest['Active Positions']))
    #     except:
    #         st.caption("Live metrics unavailable. Run backtest to generate ledger.")

    with col_btn:
        if st.button("🔥 Run Analysis", use_container_width=True, type="primary"):
            with st.spinner("Calculating..."):
                # Backend logic execution
                symbols_df = pd.read_csv(paths['symbols_file'])
                universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
                
                data_mgr = DataManager(universe, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), live_mode=True)
                prices = data_mgr.fetch_data()
                momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
                rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])
                
                bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
                weekly_bench_prices = bench_prices.resample('W-FRI').last().dropna()
                weekly_bench_roc = weekly_bench_prices.pct_change(periods=12).dropna()

                # bench_roc = data_mgr.calculate_benchmark_roc(lookback_days=regime_cfg.get('benchmark_roc_lookback', 63))
                # weekly_bench_roc = bench_roc.resample('W-FRI').last().dropna()
                
                latest_momentum = momentum_df.iloc[-1]
                latest_prices = prices.iloc[-1]
                latest_highs = rolling_highs_df.iloc[-1]
                affordable_tickers = latest_prices[latest_prices <= allocation_per_slot].index
                latest_momentum = latest_momentum.reindex(affordable_tickers).dropna()
                is_bull_market = True
                # if len(weekly_bench_roc) >= 2:
                #     curr_roc = weekly_bench_roc.iloc[-1]
                #     prev_roc = weekly_bench_roc.iloc[-2]
                #     is_bear_market = (curr_roc < 0) and (prev_roc < 0)
                #     is_bull_market = not is_bear_market
                # else:
                #     curr_roc = weekly_bench_roc.iloc[-1]
                #     prev_roc = 0.0
                #     is_bull_market = curr_roc >= 0

                st.session_state.is_bull_market = is_bull_market

                # Target Generation
                strategy = MomentumStrategy(
                    portfolio_size=strat_cfg['portfolio_size'], entry_rank=strat_cfg['entry_rank'],
                    exit_rank=strat_cfg['exit_rank'], drawdown_limit=strat_cfg['drawdown_limit']
                )
                
                current_tickers = list(current_positions.keys())
                liquidate_on_bear = regime_cfg.get('liquidate_on_bear_market', False)
                
                if is_bull_market:
                    target_portfolio = strategy.get_target_portfolio(latest_momentum, current_tickers, latest_prices, latest_highs, market_bullish=is_bull_market)
                else:
                    target_portfolio = [] if liquidate_on_bear else strategy.get_target_portfolio(latest_momentum, current_tickers, latest_prices, latest_highs, market_bullish=is_bull_market)

                # Reconcile Delta
                sells = [t for t in current_tickers if t not in target_portfolio]
                buys = [t for t in target_portfolio if t not in current_tickers]
                holds = [t for t in current_tickers if t in target_portfolio]
                
                new_positions, executed_trades, proposed_sells, proposed_buys, proposed_holds = {}, [], [], [], []
                
                for ticker in sells:
                    shares = current_positions[ticker]
                    price = latest_prices.get(ticker, 0)
                    proposed_sells.append({"Ticker": ticker, "Action": "SELL ALL", "Shares": shares, "Price": f"₹{price:.2f}"})
                    executed_trades.append({'Date': run_date, 'Action': 'SELL', 'Ticker': ticker, 'Shares': shares, 'Execution_Price': round(price, 2), 'Total_Amount': round(shares * price, 2)})
                    
                for ticker in buys:
                    price = latest_prices.get(ticker, 0)
                    if pd.notna(price) and price > 0:
                        shares = math.floor(allocation_per_slot / price)
                        cost = shares * price
                        proposed_buys.append({"Ticker": ticker, "Action": "BUY", "Shares": shares, "Price": f"₹{price:.2f}", "Cost": f"₹{cost:,.0f}"})
                        new_positions[ticker] = shares
                        executed_trades.append({'Date': run_date, 'Action': 'BUY', 'Ticker': ticker, 'Shares': shares, 'Execution_Price': round(price, 2), 'Total_Amount': round(cost, 2)})
                        
                for ticker in holds:
                    shares = current_positions[ticker]
                    proposed_holds.append({"Ticker": ticker, "Shares": shares})
                    new_positions[ticker] = shares

                # Save to session state
                st.session_state.signals_generated = True
                st.session_state.proposed_sells = proposed_sells
                st.session_state.proposed_buys = proposed_buys
                st.session_state.proposed_holds = proposed_holds
                st.session_state.new_positions = new_positions
                st.session_state.executed_trades = executed_trades

    st.markdown("---") # A simple, thin markdown line instead of the bulky st.divider()

    # --- ZONE 2: ACTION LEDGER ---
    if st.session_state.signals_generated:
        
        # Micro-Banner for Regime Status
        if st.session_state.is_bull_market:
            st.success(f"🟢 **BULLISH** | Nifty 500 ROC: {st.session_state.curr_roc * 100:.2f}% | Deploying to Top 10", icon="✅")
        else:
            st.error(f"🔴 **BEARISH** | Nifty 500 ROC: {st.session_state.curr_roc * 100:.2f}% | 50/50 Liquidcase & Gold Barbell", icon="⚠️")

        col_s, col_b = st.columns(2)
        
        with col_s:
            st.markdown(f"**📉 Sells Required ({len(st.session_state.proposed_sells)})**")
            if st.session_state.proposed_sells:
                st.dataframe(pd.DataFrame(st.session_state.proposed_sells), hide_index=True, use_container_width=True)
            else:
                st.info("No liquidations required.")
                
        with col_b:
            st.markdown(f"**📈 Buys Required ({len(st.session_state.proposed_buys)})**")
            if st.session_state.proposed_buys:
                st.dataframe(pd.DataFrame(st.session_state.proposed_buys), hide_index=True, use_container_width=True)
            else:
                st.info("No deployments required.")

        # Hide holds in an expander to save vertical space
        with st.expander(f"🔵 Active Holds Maintained ({len(st.session_state.proposed_holds)})"):
            if st.session_state.proposed_holds:
                st.dataframe(pd.DataFrame(st.session_state.proposed_holds), hide_index=True, use_container_width=True)
            else:
                st.write("No active holds.")

        # --- ZONE 3: EXECUTION ---
        if st.session_state.proposed_buys or st.session_state.proposed_sells:
            st.markdown("<br>", unsafe_allow_html=True) # Tiny bit of breathing room before the critical button
            if st.button("✅ Confirm Trades Executed in Broker (Update Ledger)", type="primary", use_container_width=True):
                save_new_positions(st.session_state.new_positions, paths.get('holdings_file', 'current_holdings.csv'))
                append_to_journal(st.session_state.executed_trades, paths.get('journal_file', 'trading_journal.csv'))
                
                st.success("Ledgers Updated Successfully!")
                st.balloons()
                st.session_state.signals_generated = False
        else:
            st.success("Portfolio is perfectly synced with the math. See you next Friday.")

if __name__ == "__main__":
    main()