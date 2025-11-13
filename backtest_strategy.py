import vectorbt as vbt
import yfinance as yf
import pandas as pd
import numpy as np

# Read symbols from CSV
symbols_df = pd.read_csv('./REF_DATA/symbols.csv')
symbols = symbols_df['Symbol'].tolist()

# Strategy parameters
fast_window = 20
slow_window = 50
stoploss_pct = None
start_date = '2024-01-01'
end_date = '2024-12-31'
refresh_data = False  # Set to False to load from storage
results = {}

for symbol in symbols:
    print(f'Processing {symbol}')
    if refresh_data:
        print(f'Downloading data for {symbol}')
        # Download stock data
        data = yf.download(f'{symbol}.NS', start=start_date, end=end_date,
                            multi_level_index = False)
        if data.empty:
            print(f"No data for {symbol}, skipping.")
            continue
        # Save to CSV with symbol name
        data = data.round(2)
        filename = f'./data/{symbol}_{start_date}_{end_date}.csv'
        data.to_csv(filename)
    else:
        print(f'Loading data for {symbol} from storage')
        # Load data from CSV
        filename = f'./data/{symbol}_{start_date}_{end_date}.csv'
        try:
            data = pd.read_csv(filename)
        except:
            print(f"File not found for {symbol}, skipping.")
            continue
    close = data['Close']
    
    # Calculate MAs
    fast_ma = close.vbt.rolling_mean(fast_window)
    slow_ma = close.vbt.rolling_mean(slow_window)

    # Signals
    entries = fast_ma > slow_ma
    exits = fast_ma < slow_ma

    # Backtest
    pf = vbt.Portfolio.from_signals(close, entries, exits, freq='1D', init_cash=10000,
                                    sl_stop=stoploss_pct, sl_trail=False)

    # Store stats
    stats = pf.stats()
    results[symbol] = stats

# Combine results into a DataFrame for summary
summary_df = pd.DataFrame(results).T
summary_df.replace([np.inf, -np.inf], np.nan,inplace=True)
summary_df.to_csv('./results/backtest_summary.csv')
print(f"Strategy Profit Factor: {summary_df['Profit Factor'].mean()}")
print(f"Strategy Expectancy: {summary_df['Expectancy'].mean()}")

# Save overall strategy summary
strategy_summary = {}
strategy_summary['Strategy_Description'] = f'MA Crossover {fast_window}/{slow_window} with {stoploss_pct} Stoploss'
strategy_summary['Start_Date'] = start_date
strategy_summary['End_Date'] = end_date
strategy_summary['Profit_Factor'] = summary_df['Profit Factor'].mean()
strategy_summary['Expectancy'] = summary_df['Expectancy'].mean()    
strategy_summary_df = pd.DataFrame([strategy_summary])
df = pd.read_csv('./results/strategy_summary.csv') if pd.io.common.file_exists('./results/strategy_summary.csv') else pd.DataFrame()
final_summary_df = pd.concat([df, strategy_summary_df], ignore_index=True)
final_summary_df.to_csv('./results/strategy_summary.csv', index=False)