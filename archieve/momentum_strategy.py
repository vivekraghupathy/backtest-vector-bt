import vectorbt as vbt
import yfinance as yf
import pandas as pd
import numpy as np
pd.set_option('display.max_rows', None)

## Strategy parameters
start_date = '2020-10-31'
end_date = '2025-10-31'
lookback = 126  # approx 6 months (trading days)
entry_count = 10
exit_rank_thresh = 20
rebalance_freq = 'M'  # 'M' for month end, can use 'W' for weekly
capital = 100000  # Example: ₹10L starting capital
refresh_data = False  # Set to False to load from storage
results = {}

# Read symbols from CSV
symbols_df = pd.read_csv('./REF_DATA/symbols.csv')
symbols = symbols_df['Symbol'].tolist()
symbols = [sym + '.NS' for sym in symbols]
if refresh_data:
    # Download data
    data = yf.download(symbols, start=start_date, 
                       end=end_date, 
                       threads=True,
                       )['Close']
    filename = f'./data/consolidated_data_{start_date}_{end_date}.csv'
    data.to_csv(filename)
else:
    filename = f'./data/consolidated_data_{start_date}_{end_date}.csv'
    data = pd.read_csv(filename,index_col=0,parse_dates=True)

# Calculate 6-month returns for ranking
returns_6m = data.pct_change(lookback,fill_method=None)

# Generate ranks, lower rank = higher momentum
ranks = returns_6m.rank(axis=1, method='min', ascending=False)
# Rebalance dates (month end)
rebalance_dates = data.groupby(data.index.to_period('M')).apply(lambda x: x.index[-1])
rebalance_dates = rebalance_dates.to_list()

# Initialize portfolio holdings DataFrame
holdings = pd.DataFrame(index=data.index, columns=data.columns)
# Main Logic: Entry/Exit based on rank at each rebalance point
current_holdings = set()
universe = set(symbols)
for dt in rebalance_dates:
    temp = current_holdings.copy()
    if dt not in ranks.index:
        print(f"Date {dt} not in ranks index, skipping.")
        continue
    # Find momentum ranks at this rebalance date
    day_ranks = ranks.loc[dt]
    # Stocks eligible for holding (in the current portfolio) — remove below threshold
    kept = {sym for sym in current_holdings if (sym in day_ranks.index and day_ranks[sym] <= exit_rank_thresh)}
    # Stocks to newly enter: Top N not already kept
    select = day_ranks.nsmallest(entry_count).index
    new_buys = set(select) - kept
    # Update current holdings
    current_holdings = kept | new_buys
    sells = temp - current_holdings
    non_holdings = universe - current_holdings
    # Mark holdings
    if dt in holdings.index:
        holdings.loc[dt, list(current_holdings)] = True
        holdings.loc[dt, list(non_holdings)] = False

# Forward-fill holdings to all days till next rebalance
holdings = holdings.ffill().fillna(False)
# Generate entry/exit signals
entries = holdings
exits = ~holdings
entries.to_csv('./results/momentum_strategy_entries.csv')
exits.to_csv('./results/momentum_strategy_exits.csv')

# Run backtest on vectorbt
pf = vbt.Portfolio.from_signals(
    data, 
    entries, 
    exits, 
    freq='1D', 
    init_cash=10000, 
    direction='longonly',
    # Set other arguments as needed
)
# Analyze performance
stats = pf.stats()
trades_df = pf.trades.records_readable
trades_df.to_csv('./results/momentum_strategy_trades.csv')
print(stats)  