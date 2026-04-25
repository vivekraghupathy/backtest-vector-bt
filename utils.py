import pandas as pd
master_file = 'nifty500_master_10yr.parquet'
cutoff_date = '2026-04-24'
df = pd.read_parquet(master_file)
df.index = pd.to_datetime(df.index)

initial_rows = len(df)
latest_existing_date = df.index.max().strftime('%Y-%m-%d')
print(f"-> Current Latest Date in file: {latest_existing_date}")
print(f"-> Initial Total Days: {initial_rows}")
filtered_df = df.loc[:cutoff_date]
final_rows = len(filtered_df)
rows_deleted = initial_rows - final_rows
print(f"-> Rows Deleted: {rows_deleted}")
filtered_df.to_parquet(master_file)
new_latest_date = filtered_df.index.max().strftime('%Y-%m-%d')
print(f"\n✅ SUCCESS: Trimmed database saved to [{master_file}]")
print(f"-> Deleted {rows_deleted} rows.")
print(f"-> New Latest Date: {new_latest_date}")
print(f"-> New Total Days: {final_rows}")