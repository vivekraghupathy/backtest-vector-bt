import pandas as pd
import numpy as np

class TradeAnalyzer:
    def __init__(self, trades_df):
        """
        Expects a Pandas DataFrame containing the Universal Trade Ledger schema.
        """
        self.trades = trades_df
        
        # Ensure data types are correct upon initialization
        if not self.trades.empty:
            self.trades['Entry_Date'] = pd.to_datetime(self.trades['Entry_Date'])
            self.trades['Exit_Date'] = pd.to_datetime(self.trades['Exit_Date'])
            self.trades['PnL_Pct'] = self.trades['PnL_Pct'].astype(float)
            self.trades['Days_Held'] = self.trades['Days_Held'].astype(int)

    def generate_report(self):
        """Calculates institutional metrics and returns a dictionary of results."""
        if self.trades.empty:
            return {"Error": "No closed trades available to analyze."}

        # Separate winners and losers
        winners = self.trades[self.trades['PnL_Pct'] > 0]
        losers = self.trades[self.trades['PnL_Pct'] <= 0]

        # 1. Mechanics
        total_trades = len(self.trades)
        win_rate = (len(winners) / total_trades) * 100
        
        avg_win = winners['PnL_Pct'].mean() * 100 if not winners.empty else 0.0
        avg_loss = abs(losers['PnL_Pct'].mean()) * 100 if not losers.empty else 0.0
        
        payoff_ratio = (avg_win / avg_loss) if avg_loss != 0 else float('inf')

        # 2. Portfolio Impact
        gross_profit = winners['PnL_Pct'].sum()
        gross_loss = abs(losers['PnL_Pct'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss != 0 else float('inf')

        # 3. Extremes and Time
        max_profit = self.trades['PnL_Pct'].max() * 100
        max_loss = self.trades['PnL_Pct'].min() * 100
        avg_days_held = self.trades['Days_Held'].mean()

        return {
            "Total_Trades": total_trades,
            "Win_Rate_Pct": round(win_rate, 2),
            "Profit_Factor": round(profit_factor, 2),
            "Payoff_Ratio": round(payoff_ratio, 2),
            "Average_Win_Pct": round(avg_win, 2),
            "Average_Loss_Pct": round(avg_loss, 2),
            "Max_Single_Profit_Pct": round(max_profit, 2),
            "Max_Single_Loss_Pct": round(max_loss, 2),
            "Average_Days_Held": round(avg_days_held, 0)
        }

    def print_tearsheet(self):
        """Prints a beautifully formatted dashboard to the console."""
        metrics = self.generate_report()
        
        if "Error" in metrics:
            print(metrics["Error"])
            return

        print("\n============================================================")
        print("QUANTITATIVE PERFORMANCE TEARSHEET")
        print("============================================================")
        print(f"Total Completed Trades: {metrics['Total_Trades']}")
        print(f"Win Rate:               {metrics['Win_Rate_Pct']}%")
        print(f"Profit Factor:          {metrics['Profit_Factor']}")
        print(f"Payoff Ratio:           {metrics['Payoff_Ratio']}")
        print("------------------------------------------------------------")
        print(f"Average Win:           +{metrics['Average_Win_Pct']}%")
        print(f"Average Loss:          -{metrics['Average_Loss_Pct']}%")
        print(f"Max Single Profit:     +{metrics['Max_Single_Profit_Pct']}%")
        print(f"Max Single Loss:       -{metrics['Max_Single_Loss_Pct']}%")
        print(f"Average Days Held:      {metrics['Average_Days_Held']} days")
        print("============================================================\n")


def convert_journal_to_ledger(csv_path):
    """
    Reads a live Event Ledger CSV and converts it into a Round-Trip 
    Universal Trade Ledger DataFrame suitable for the TradeAnalyzer.
    """
    # 1. Load the raw journal
    try:
        raw_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: Could not find {csv_path}")
        return pd.DataFrame()

    # Ensure Date is a proper datetime object
    raw_df['Date'] = pd.to_datetime(raw_df['Date'])
    
    open_positions = {}
    closed_trades = []
    
    # 2. Iterate chronologically through the raw transactions
    for index, row in raw_df.iterrows():
        ticker = row['Ticker']
        if ticker == 'GOLDBEES.NS':
            continue
        action = row['Action']
        date = row['Date']
        price = row['Price']
        
        if action == 'BUY':
            # We store the entry data in our holding pen.
            # (Note: This assumes you only buy a ticker once before selling it. 
            # If you already own it and buy more, this will overwrite the original entry price).
            open_positions[ticker] = {
                'Entry_Date': date,
                'Entry_Price': price
            }
            
        elif action == 'SELL':
            # When we hit a SELL, we match it to the open position
            if ticker in open_positions:
                entry_data = open_positions.pop(ticker)
                
                # Calculate the exact metrics the Analyzer needs
                pnl_pct = (price - entry_data['Entry_Price']) / entry_data['Entry_Price']
                days_held = (date - entry_data['Entry_Date']).days
                
                # Append the completed round-trip to the ledger
                closed_trades.append({
                    'Ticker': ticker,
                    'Entry_Date': entry_data['Entry_Date'],
                    'Entry_Price': entry_data['Entry_Price'],
                    'Exit_Date': date,
                    'Exit_Price': price,
                    'PnL_Pct': pnl_pct,
                    'Days_Held': days_held
                })
            else:
                # This catches an edge case where you sell a stock that wasn't 
                # recorded as a BUY in this specific CSV file.
                print(f"Warning: Found SELL for {ticker} on {date.date()} but no matching BUY record.")

    # 3. Convert the completed ledger to a DataFrame
    trades_df = pd.DataFrame(closed_trades)
    
    if trades_df.empty:
         print("Warning: No completed round-trip trades found in the journal.")
         
    return trades_df

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

if __name__ == "__main__":
    file_to_run = "backtest_trade_journal.csv"
    ledger_df = convert_journal_to_ledger(file_to_run)
    # Run the math and print the tearsheet
    if not ledger_df.empty:
        analyzer = TradeAnalyzer(ledger_df)
        analyzer.print_tearsheet()
    else:
        print("\nWarning: No completed round-trip trades found to analyze.")