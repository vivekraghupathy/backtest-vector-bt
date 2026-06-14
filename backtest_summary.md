# Backtest Run History

This file tracks the rules, parameters, and performance results of each backtest execution.

---

## Run 1: Basic Momentum with Bear Market Liquidation
* **Execution Date**: 2026-06-06
* **Regime Filter**: Bullish if Benchmark (`^CRSLDX`) > 200DMA. **Liquidate completely on Bear Market = True**.
* **Entry Rules**: Top 10 by 60-day ROC, close > 90% of 60-day rolling high.
* **Exit Rules**: Rank > 50 OR close $\le$ 90% of 60-day rolling high.
* **Capital Rules**: INR 25,000 allocation per slot (INR 250,000 initial capital), W-FRI rebalancing.

### Performance Results
| Metric | Strategy | Benchmark |
| :--- | :--- | :--- |
| **Absolute Return** | 6043.97% | 271.93% |
| **CAGR** | 50.95% | 14.04% |
| **Max Drawdown** | -21.89% | -38.30% |
| **Alpha (CAGR Diff)** | +36.91% | - |
| **Total Trades** | 668 | - |

### Trade Analytics
* **Win Rate**: 45.21%
* **Profit Factor**: 2.63
* **Payoff Ratio**: 3.19
* **Average Win / Loss**: +22.56% / -7.08%
* **Average Days Held**: 34.0 days

---

## Run 2: Basic Momentum (No Bear Market Liquidation)
* **Execution Date**: 2026-06-06
* **Regime Filter**: Bullish if Benchmark (`^CRSLDX`) > 200DMA. **Liquidate completely on Bear Market = False** (just block new entries).
* **Entry Rules**: Top 10 by 60-day ROC, close > 90% of 60-day rolling high.
* **Exit Rules**: Rank > 50 OR close $\le$ 90% of 60-day rolling high.
* **Capital Rules**: INR 25,000 allocation per slot (INR 250,000 initial capital), W-FRI rebalancing.

### Performance Results
| Metric | Strategy | Benchmark |
| :--- | :--- | :--- |
| **Absolute Return** | 5322.45% | 271.93% |
| **CAGR** | 49.07% | 14.04% |
| **Max Drawdown** | -20.02% | -38.30% |
| **Alpha (CAGR Diff)** | +35.04% | - |
| **Total Trades** | 641 | - |

### Trade Analytics
* **Win Rate**: 43.99%
* **Profit Factor**: 2.71
* **Payoff Ratio**: 3.45
* **Average Win / Loss**: +25.06% / -7.26%
* **Average Days Held**: 37.0 days
---

## Run 3: Manual Backtest Run
* **Execution Date**: 2026-06-06
* **Regime Filter**: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Entry Rules**: Top 10 by 60-day ROC, close > 90% of rolling high.
* **Exit Rules**: Rank > 50 OR close $\le$ 90% of rolling high.
* **Capital Rules**: Allocation per slot = 25000, rebalance frequency = W-FRI.

### Performance Results
| Metric | Strategy | Benchmark |
| :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 271.93% |
| **CAGR** | 49.86% | 14.04% |
| **Max Drawdown** | -28.09% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | - |
| **Total Trades** | 632 | - |

### Trade Analytics
* **Win Rate**: 44.94%
* **Profit Factor**: 2.75
* **Payoff Ratio**: 3.37
* **Average Win / Loss**: +25.2% / -7.47%
* **Average Days Held**: 38.0 days

---

## Run 4: Manual Backtest Run
* **Execution Date**: 2026-06-07
* **Regime Filter**: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Entry Rules**: Top 10 by 60-day ROC, close > 90% of rolling high.
* **Exit Rules**: Rank > 50 OR close $\le$ 90% of rolling high.
* **Capital Rules**: Allocation per slot = 25000, rebalance frequency = W-FRI.

### Performance Results
| Metric | Strategy | Benchmark |
| :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 271.93% |
| **CAGR** | 49.86% | 14.04% |
| **Max Drawdown** | -28.09% | -38.30% |

---

## Run 3: Pure Momentum Baseline
* **Execution Date**: 2026-06-06
* **Regime Filter**: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Entry Rules**: Top 10 by 60-day ROC, close > 90% of rolling high.
* **Exit Rules**: Rank > 50 OR close $\le$ 90% of rolling high.
* **Capital Rules**: Allocation per slot = 25000, rebalance frequency = W-FRI.

### Performance Results
| Metric | Strategy | Benchmark |
| :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 271.93% |
| **CAGR** | 49.86% | 14.04% |
| **Max Drawdown** | -28.09% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | - |
| **Total Trades** | 632 | - |

### Trade Analytics
* **Win Rate**: 44.94%
* **Profit Factor**: 2.75
* **Payoff Ratio**: 3.37
* **Average Win / Loss**: +25.2% / -7.47%
* **Average Days Held**: 38.0 days

---

## Run 4: Parallel Run (Momentum vs Barbell) - Static 50/50 safe allocation
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: 50% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: 50% in 5 momentum slots.
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 1607.45% | 271.93% |
| **CAGR** | 49.86% | 32.81% | 14.04% |
| **Max Drawdown** | -28.09% | -16.52% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | +18.77% | - |
| **Total Trades** | 632 | 1612 | - |

### Trade Analytics
* **Win Rate**: Momentum = 44.94% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.75 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.37 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +25.2% / -7.47% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 5: Parallel Run (Momentum vs Barbell) - Option 1: Dynamic Split
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 2486.68% | 271.93% |
| **CAGR** | 49.86% | 38.44% | 14.04% |
| **Max Drawdown** | -28.09% | -29.59% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | +24.40% | - |
| **Total Trades** | 632 | 1611 | - |

### Trade Analytics
* **Win Rate**: Momentum = 44.94% | Barbell = 43.78%
* **Profit Factor**: Momentum = 2.75 | Barbell = 2.07
* **Payoff Ratio**: Momentum = 3.37 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +25.2% / -7.47% | Barbell = +20.03% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days
---

## Run 8: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 2422.65% | 271.93% |
| **CAGR** | 49.86% | 38.09% | 14.04% |
| **Max Drawdown** | -28.09% | -29.62% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | +24.06% | - |
| **Total Trades** | 632 | 1467 | - |

### Trade Analytics
* **Win Rate**: Momentum = 44.94% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.75 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.37 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +25.2% / -7.47% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 9: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 200dma. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 5617.90% | 2422.65% | 271.93% |
| **CAGR** | 49.86% | 38.09% | 14.04% |
| **Max Drawdown** | -28.09% | -29.62% | -38.30% |
| **Alpha (CAGR Diff)** | +35.83% | +24.06% | - |
| **Total Trades** | 632 | 1467 | - |

### Trade Analytics
* **Win Rate**: Momentum = 44.94% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.75 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.37 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +25.2% / -7.47% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 10: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > none. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 11138.44% | 2925.14% | 271.93% |
| **CAGR** | 60.34% | 40.62% | 14.04% |
| **Max Drawdown** | -29.09% | -24.54% | -38.30% |
| **Alpha (CAGR Diff)** | +46.31% | +26.59% | - |
| **Total Trades** | 813 | 1466 | - |

### Trade Analytics
* **Win Rate**: Momentum = 46.18% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.6 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.03 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +23.64% / -7.79% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 11: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > none. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 11138.44% | 2925.14% | 271.93% |
| **CAGR** | 60.34% | 40.62% | 14.04% |
| **Max Drawdown** | -29.09% | -24.54% | -38.30% |
| **Alpha (CAGR Diff)** | +46.31% | +26.59% | - |
| **Total Trades** | 813 | 1466 | - |

### Trade Analytics
* **Win Rate**: Momentum = 46.18% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.6 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.03 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +23.64% / -7.79% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 12: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 50d_breakout. **Liquidate completely on Bear Market = True**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 11420.27% | 2544.25% | 271.93% |
| **CAGR** | 60.74% | 38.74% | 14.04% |
| **Max Drawdown** | -32.91% | -30.35% | -38.30% |
| **Alpha (CAGR Diff)** | +46.70% | +24.71% | - |
| **Total Trades** | 649 | 1463 | - |

### Trade Analytics
* **Win Rate**: Momentum = 45.99% | Barbell = 44.04%
* **Profit Factor**: Momentum = 2.8 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.29 | Barbell = 2.64
* **Average Win / Loss**: Momentum = +24.94% / -7.59% | Barbell = +19.98% / -7.56%
* **Average Days Held**: Momentum = 36.0 days | Barbell = 31.0 days

---

## Run 13: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 50d_breakout. **Liquidate completely on Bear Market = True**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 5012.82% | 2544.25% | 271.93% |
| **CAGR** | 48.20% | 38.74% | 14.04% |
| **Max Drawdown** | -36.81% | -30.35% | -38.30% |
| **Alpha (CAGR Diff)** | +34.16% | +24.71% | - |
| **Total Trades** | 563 | 1463 | - |

### Trade Analytics
* **Win Rate**: Momentum = 47.25% | Barbell = 44.04%
* **Profit Factor**: Momentum = 2.54 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 2.84 | Barbell = 2.64
* **Average Win / Loss**: Momentum = +22.07% / -7.77% | Barbell = +19.98% / -7.56%
* **Average Days Held**: Momentum = 35.0 days | Barbell = 31.0 days

---

## Run 14: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > 50d_breakout. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 7011.70% | 2544.25% | 271.93% |
| **CAGR** | 53.17% | 38.74% | 14.04% |
| **Max Drawdown** | -39.76% | -30.35% | -38.30% |
| **Alpha (CAGR Diff)** | +39.13% | +24.71% | - |
| **Total Trades** | 640 | 1463 | - |

### Trade Analytics
* **Win Rate**: Momentum = 45.07% | Barbell = 44.04%
* **Profit Factor**: Momentum = 2.76 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.36 | Barbell = 2.64
* **Average Win / Loss**: Momentum = +26.15% / -7.78% | Barbell = +19.98% / -7.56%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 15: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > none. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 11138.44% | 2925.14% | 271.93% |
| **CAGR** | 60.34% | 40.62% | 14.04% |
| **Max Drawdown** | -29.09% | -24.54% | -38.30% |
| **Alpha (CAGR Diff)** | +46.31% | +26.59% | - |
| **Total Trades** | 813 | 1466 | - |

### Trade Analytics
* **Win Rate**: Momentum = 46.18% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.6 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 3.03 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +23.64% / -7.79% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 38.0 days | Barbell = 31.0 days

---

## Run 16: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 10 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 40 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > none. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 7513.93% | 2925.14% | 271.93% |
| **CAGR** | 54.22% | 40.62% | 14.04% |
| **Max Drawdown** | -32.33% | -24.54% | -38.30% |
| **Alpha (CAGR Diff)** | +40.18% | +26.59% | - |
| **Total Trades** | 872 | 1466 | - |

### Trade Analytics
* **Win Rate**: Momentum = 44.89% | Barbell = 43.96%
* **Profit Factor**: Momentum = 2.34 | Barbell = 2.08
* **Payoff Ratio**: Momentum = 2.87 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +22.08% / -7.69% | Barbell = +19.98% / -7.55%
* **Average Days Held**: Momentum = 35.0 days | Barbell = 31.0 days

---

## Run 17: Parallel Run (Momentum vs Barbell)
* **Execution Date**: 2026-06-07
* **Momentum Setup**:
  * Entry: Top 15 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 50 OR close $\le$ 90% of rolling high.
  * Regime Filter: Bullish if Benchmark > none. **Liquidate completely on Bear Market = False**.
* **Barbell Setup**:
  * Safe Allocation: Bull = 30%, Bear = 80% (Split: 50% Gold / 50% Cash).
  * Risk Allocation: Bull = 70%, Bear = 20% in 5 momentum slots.
  * Gold Trend Filter: True (Lookback: 50 days).
  * Entry: Top 5 by 60-day ROC, close > 90% of rolling high.
  * Exit: Rank > 25 OR close $\le$ 90% of rolling high.
  * Regime Filter: **Ignored (always trades risk leg)**. Rebalancing is frictionless (no stock resizing).

### Performance Results
| Metric | Momentum Strategy | Barbell Strategy | Benchmark (^CRSLDX) |
| :--- | :--- | :--- | :--- |
| **Absolute Return** | 6674.12% | 2907.30% | 271.93% |
| **CAGR** | 52.43% | 40.54% | 14.04% |
| **Max Drawdown** | -27.56% | -24.57% | -38.30% |
| **Alpha (CAGR Diff)** | +38.39% | +26.50% | - |
| **Total Trades** | 1266 | 1468 | - |

### Trade Analytics
* **Win Rate**: Momentum = 45.93% | Barbell = 43.88%
* **Profit Factor**: Momentum = 2.39 | Barbell = 2.07
* **Payoff Ratio**: Momentum = 2.81 | Barbell = 2.65
* **Average Win / Loss**: Momentum = +21.48% / -7.64% | Barbell = +19.98% / -7.54%
* **Average Days Held**: Momentum = 37.0 days | Barbell = 31.0 days

