"""
Trade Journal & Output Schemas — standardized, auditable, machine-readable.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
import json, datetime


@dataclass
class TradeRecord:
    """Single trade execution record."""
    action: str  # BUY | SELL
    date: str
    price: float
    executed_price: float
    reason: str = ""
    pnl_pct: Optional[float] = None
    units: Optional[float] = None
    fee: Optional[float] = None
    capital_deployed: Optional[float] = None
    recorded_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())


@dataclass
class BacktestOutput:
    """Standardized backtest output."""
    strategy: str
    symbol: str
    start_date: str
    end_date: str
    trades: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())


@dataclass
class MetricsOutput:
    """Standardized metrics container."""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    years: float = 0.0
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    win_rate_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_loss_ratio: Optional[float] = None
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_dd_duration_periods: int = 0
    calmar_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy_pct: float = 0.0
    gross_profit_pct: float = 0.0
    gross_loss_pct: float = 0.0
    volatility_annualized_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def validate_trade(trade: dict) -> bool:
    """Check required trade fields."""
    required = ["action", "date", "price"]
    return all(k in trade for k in required)


def load_journal(path: str = "trade_journal.json") -> dict:
    """Load trade journal, create if missing."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"trades": [], "observations": [], "status": "active"}


def save_journal(journal: dict, path: str = "trade_journal.json"):
    """Save trade journal."""
    with open(path, "w") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False, default=str)
