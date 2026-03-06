@echo off

title Momentum Strategy - Weekly Rebalance

echo ===================================================
echo Starting Weekly Rebalance Engine...
echo ===================================================

:: 1. Navigate to your project directory
cd /d "C:\Users\vivek\repo\backtest-vector-bt\"

:: 2. Run the Python script
python weekly_rebalance.py

:: 3. Keep the window open so you can read the signals and confirm
echo.
pause