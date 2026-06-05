"""
V5 MoonReversal — Centralized Configuration
All tunable parameters live here. No magic numbers in strategy code.
"""

# ═══════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════
SYMBOLS = ["BTCUSDT"]
VALIDATION_SYMBOLS = ["ETHUSDT", "SOLUSDT"]
TIMEFRAMES = {
    "monthly": "1M",
    "weekly": "1w",
    "daily": "1d",
}
BINANCE_BASE = "https://api.binance.com/api/v3/klines"
MONTHLY_LIMIT = 48
WEEKLY_LIMIT = 208
DAILY_LIMIT = 365

# ═══════════════════════════════════════════════════════════
# STRATEGY: Moon Reversal
# ═══════════════════════════════════════════════════════════
STRATEGY = {
    # Entry
    "bear_definition": "close < open",  # Red monthly candle
    "entry_trigger": "first_green_week",  # First green weekly after bear month

    # Exit A: Consecutive red weeks
    "exit_confirmation_weeks": 2,

    # Exit B: Trailing stop
    "trailing_activation_pct": 5.0,   # % gain before trailing stop activates
    "trailing_distance_pct": 4.0,     # % drop from peak to trigger exit

    # Position sizing
    "kelly_fraction": 0.5,            # Half Kelly
    "kelly_cap": 0.40,                # Absolute maximum allocation
    "runner_pct": 0.30,               # % of position left as runner (future)

    # Risk limits
    "max_consecutive_losses": 3,      # Pause after N consecutive losses
    "max_single_loss_pct": 20.0,      # Alert threshold
}

# ═══════════════════════════════════════════════════════════
# EXECUTION REALISM
# ═══════════════════════════════════════════════════════════
EXECUTION = {
    "fee_pct": 0.10,                  # Taker fee (0.1% = Binance standard)
    "slippage_pct": 0.20,             # Estimated slippage
    "spread_pct": 0.02,               # Bid-ask spread assumption
    "stop_gap_risk_pct": 0.50,        # Worst-case gap through stop (%)
    "min_liquidity_usd": 5_000_000,   # Minimum 24h volume to trade
}

# ═══════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════
BACKTEST = {
    "initial_capital": 10_000,        # HKD baseline
    "currency": "HKD",
    "compound": True,                 # Compound returns or arithmetic sum

    # Walk-forward
    "wf_train_years": 2,
    "wf_test_years": 1,
    "wf_step_months": 3,

    # Rolling window
    "window_years": 2,
    "shift_months": 3,

    # Monte Carlo
    "mc_simulations": 10_000,
    "mc_confidence": 0.95,
}

# ═══════════════════════════════════════════════════════════
# BENCHMARKS
# ═══════════════════════════════════════════════════════════
BENCHMARKS = {
    "buy_hold": ["BTCUSDT", "ETHUSDT"],
    "cash_return_pct": 0.0,           # Annual cash return assumption
}

# ═══════════════════════════════════════════════════════════
# REGIME CLASSIFICATION
# ═══════════════════════════════════════════════════════════
REGIME = {
    "lookback_months": 6,
    "bull_threshold_pct": 10.0,       # >10% in lookback = bull
    "bear_threshold_pct": -10.0,      # <-10% in lookback = bear
    "panic_vix_equivalent": 40,       # High vol threshold (proxy)
}

# ═══════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════
MONITORING = {
    "check_interval": "weekly",
    "alert_win_rate_deviation": 30,   # % deviation from baseline before alert
    "alert_max_drawdown_ratio": 1.5,  # × baseline max DD before alert
    "baseline": {
        "win_rate": 0.87,
        "avg_win_pct": 6.4,
        "avg_loss_pct": 12.4,
        "max_drawdown_pct": 13.8,
        "trades_per_year": 3.75,
        "total_return_pct": 60.8,
        "kelly": 0.746,
    },
}

# ═══════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════
REPORTING = {
    "output_dir": "reports",
    "chart_style": "dark_background",
    "dpi": 150,
    "formats": ["png", "json"],
}

# ═══════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════
LOGGING = {
    "level": "INFO",
    "format": "json",                 # json | text
    "log_dir": "logs",
    "trade_log": "logs/trades.jsonl",
    "error_log": "logs/errors.jsonl",
}
