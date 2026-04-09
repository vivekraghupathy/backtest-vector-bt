import os
import pandas as pd
import math
from datetime import datetime, timedelta
import streamlit as st

# Import your shared brain
from core import DataManager, MomentumStrategy, ConfigLoader

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Quant Command | Friday Rebalance", page_icon="⚙️", layout="wide")

# ==========================================
# FILE MANAGEMENT FUNCTIONS (From Terminal Script)
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
# Initialize session state variables to hold data between clicks
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
    st.title("⚙️ Institutional Momentum Engine")
    run_date = datetime.now().strftime('%Y-%m-%d')
    st.markdown(f"**Execution Date:** {run_date}")
    st.divider()

    # 1. LOAD CONFIGURATION
    cfg = ConfigLoader('config.json')
    strat_cfg = cfg.get_strategy_params()
    regime_cfg = cfg.get_regime_params()
    cap_cfg = cfg.get_capital_params()
    paths = cfg.get_paths()
    allocation_per_slot = cap_cfg.get('allocation_per_slot', 25000)

    # 2. READ LIVE STATE
    current_positions = load_current_positions(paths.get('holdings_file', 'current_holdings.csv'))
    
    # --- ZONE 1: COMMAND & CONTROL ---
    col_status, col_btn = st.columns([3, 1])
    with col_status:
        st.subheader("System State")
        st.write(f"Currently tracking **{len(current_positions)}** active equity positions.")
    
    with col_btn:
        st.write("")
        if st.button("🔥 Generate Weekly Signals", use_container_width=True, type="primary"):
            with st.spinner("Parsing Universe & Calculating Matrices..."):
                # Run the exact logic from your terminal script
                symbols_df = pd.read_csv(paths['symbols_file'])
                universe = [f"{str(sym).strip()}.NS" for sym in symbols_df['Symbol'].tolist()]
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=cap_cfg['live_data_lookback_days'])
                
                data_mgr = DataManager(universe, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), live_mode=True)
                prices = data_mgr.fetch_data()
                momentum_df = data_mgr.calculate_momentum(lookback_days=strat_cfg['momentum_lookback_days'])
                rolling_highs_df = data_mgr.calculate_rolling_high(lookback_days=strat_cfg['momentum_lookback_days'])
                
                bench_prices = data_mgr.fetch_benchmark(regime_cfg['benchmark_ticker'])
                bench_roc = data_mgr.calculate_benchmark_roc(lookback_days=regime_cfg.get('benchmark_roc_lookback', 63))
                weekly_bench_roc = bench_roc.resample('W-FRI').last().dropna()
                
                latest_momentum = momentum_df.iloc[-1]
                latest_prices = prices.iloc[-1]
                latest_highs = rolling_highs_df.iloc[-1]
                
                if len(weekly_bench_roc) >= 2:
                    curr_roc = weekly_bench_roc.iloc[-1]
                    prev_roc = weekly_bench_roc.iloc[-2]
                    is_bear_market = (curr_roc < 0) and (prev_roc < 0)
                    is_bull_market = not is_bear_market
                else:
                    curr_roc = bench_roc.iloc[-1]
                    prev_roc = 0.0
                    is_bull_market = curr_roc >= 0

                st.session_state.curr_roc = curr_roc
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
                    if liquidate_on_bear:
                        target_portfolio = []
                    else:
                        target_portfolio = strategy.get_target_portfolio(latest_momentum, current_tickers, latest_prices, latest_highs, market_bullish=is_bull_market)

                # Reconcile Delta
                sells = [t for t in current_tickers if t not in target_portfolio]
                buys = [t for t in target_portfolio if t not in current_tickers]
                holds = [t for t in current_tickers if t in target_portfolio]
                
                # Build Ledgers for UI and Saving
                new_positions = {}
                executed_trades = []
                proposed_sells = []
                proposed_buys = []
                proposed_holds = []
                
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
                        proposed_buys.append({"Ticker": ticker, "Action": "BUY", "Shares": shares, "Price": f"₹{price:.2f}", "Cost": f"₹{cost:,.2f}"})
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

    st.divider()

    # --- ZONE 2: TRADE LEDGER ---
    if st.session_state.signals_generated:
        if st.session_state.is_bull_market:
            st.success(f"🟢 REGIME: BULLISH | Nifty 500 ROC: {st.session_state.curr_roc * 100:.2f}%")
        else:
            st.error(f"🔴 REGIME: BEARISH | Nifty 500 ROC: {st.session_state.curr_roc * 100:.2f}%")
            st.caption("2-Week negative confirmation met. Applying Bear Regime logic.")
            if not st.session_state.is_bull_market and regime_cfg.get('liquidate_on_bear_market', False):
                st.warning("⚠️ STATUS: MACRO FLUSH. Liquidating all equity positions. Deploying 50/50 Liquidcase & Gold.")

        st.subheader("Action Required")
        col_s, col_b = st.columns(2)
        
        with col_s:
            st.error(f"📉 SELLS: {len(st.session_state.proposed_sells)}")
            if st.session_state.proposed_sells:
                st.dataframe(pd.DataFrame(st.session_state.proposed_sells), hide_index=True, use_container_width=True)
            else:
                st.info("None")
                
        with col_b:
            st.success(f"📈 BUYS (₹{allocation_per_slot:,.0f} / slot): {len(st.session_state.proposed_buys)}")
            if st.session_state.proposed_buys:
                st.dataframe(pd.DataFrame(st.session_state.proposed_buys), hide_index=True, use_container_width=True)
            else:
                st.info("None")
                
        st.info(f"🔵 HOLDS: {len(st.session_state.proposed_holds)} existing positions kept.")

        st.divider()
        
        # --- ZONE 3: BROKER CONFIRMATION ---
        if st.session_state.proposed_buys or st.session_state.proposed_sells:
            st.subheader("Broker Sync")
            st.warning("⚠️ Only proceed if you have successfully placed and filled all the above orders in your Zerodha/broker account.")
            
            if st.button("✅ Confirm Trades Executed (Update CSVs)", type="primary"):
                save_new_positions(st.session_state.new_positions, paths.get('holdings_file', 'current_holdings.csv'))
                append_to_journal(st.session_state.executed_trades, paths.get('journal_file', 'trading_journal.csv'))
                
                st.success("State Updated! Holdings and Trading Journal have been saved.")
                st.balloons()
                
                # Reset state so the button goes away after execution
                st.session_state.signals_generated = False
        else:
            st.success("✅ No trades required today. You are fully synced with the math.")

if __name__ == "__main__":
    main()