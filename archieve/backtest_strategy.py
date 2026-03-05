import vectorbt as vbt
import yfinance as yf
import pandas as pd
import numpy as np
pd.set_option('display.max_rows', None)

# Read symbols from CSV
symbols_df = pd.read_csv('./REF_DATA/symbols.csv')
symbols = symbols_df['Symbol'].tolist()

# Strategy parameters
fast_window = 50
slow_window = 200
stoploss_pct = None
start_date = '2020-10-31'
end_date = '2025-10-31'
refresh_data = False  # Set to False to load from storage
results = {}
# ATR calculation (14 periods)
def atr(high, low, close, length=14):
    tr = np.maximum((high - low), 
                    np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    atr_val = tr.rolling(length).mean()
    return atr_val

# SuperTrend calculation
def supertrend(high, low, close, length=10, multiplier=3):
    atr_val = atr(high, low, close, length)
    hl2 = (high + low) / 2

    # Basic upper and lower bands
    upperband = hl2 + multiplier * atr_val
    lowerband = hl2 - multiplier * atr_val

    # Final bands (initially equal to basic bands)
    final_upperband = upperband.copy()
    final_lowerband = lowerband.copy()

    # Iterate to compute final bands
    for i in range(1, len(close)):
        if close[i - 1] > final_upperband[i - 1]:
            final_upperband[i] = max(upperband[i], final_upperband[i - 1])
        else:
            final_upperband[i] = upperband[i]

        if close[i - 1] < final_lowerband[i - 1]:
            final_lowerband[i] = min(lowerband[i], final_lowerband[i - 1])
        else:
            final_lowerband[i] = lowerband[i]

    # SuperTrend determination
    supertrend = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i] > final_upperband[i - 1]:
            supertrend[i] = 1  # uptrend
        elif close[i] < final_lowerband[i - 1]:
            supertrend[i] = -1  # downtrend
        else:
            supertrend[i] = supertrend[i - 1]

    return pd.Series(supertrend, index=close.index)

def SuperTrend_Strategy(high, low, close):
    strategy_desc = 'SuperTrend Strategy'
    st = supertrend(high, low, close)
    entries = st == 1
    exits = st == -1
    return entries, exits, strategy_desc

def MA_Crossover_Strategy(close, fast_window, slow_window,volume):
    strategy_desc = f'MA Crossover {fast_window}/{slow_window} with Volume surge'
    fast_ma = close.vbt.rolling_mean(fast_window)
    slow_ma = close.vbt.rolling_mean(slow_window)
    volume_ma = volume.vbt.rolling_mean(slow_window)
    trend_ma = close.vbt.rolling_mean(slow_window*2)
    entries = (fast_ma > slow_ma) & (volume > 2 * volume_ma)
    exits = (fast_ma < slow_ma)
    return entries, exits, strategy_desc    

def Trend_Pullback(close,low):
    fast_window = 10
    slow_window = 20
    trend_window = 50   

    strategy_desc = f'Pullback Trend {fast_window}/{slow_window}/{trend_window}'

    fast_ma = close.vbt.rolling_mean(fast_window)
    slow_ma = close.vbt.rolling_mean(slow_window)
    trend_ma = close.vbt.rolling_mean(trend_window)

    entries = (fast_ma > slow_ma) & (slow_ma > trend_ma) & (low < slow_ma) & (close > slow_ma)
    exits = (close < slow_ma)
    return entries, exits, strategy_desc 

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
    low = data['Low']
    volume = data['Volume']
    high = data['High']
    
    # entries, exits, strategy_desc = SuperTrend_Strategy(high, low, close)
    entries, exits, strategy_desc = MA_Crossover_Strategy(close, fast_window, slow_window,volume)
    # entries, exits, strategy_desc = Trend_Pullback(close,low)
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
print(f"Strategy Mean Return: {summary_df['Total Return [%]'].mean()}")

# Save overall strategy summary
strategy_summary = {}
strategy_summary['Strategy_Description'] = strategy_desc
strategy_summary['Start_Date'] = start_date
strategy_summary['End_Date'] = end_date
strategy_summary['Profit_Factor'] = summary_df['Profit Factor'].mean()
strategy_summary['Expectancy'] = summary_df['Expectancy'].mean() 
strategy_summary['Mean_Return_%'] = summary_df['Total Return [%]'].mean()

strategy_summary_df = pd.DataFrame([strategy_summary])
df = pd.read_csv('./results/strategy_summary.csv') if pd.io.common.file_exists('./results/strategy_summary.csv') else pd.DataFrame()
final_summary_df = pd.concat([df, strategy_summary_df], ignore_index=True)
final_summary_df.to_csv('./results/strategy_summary.csv', index=False)