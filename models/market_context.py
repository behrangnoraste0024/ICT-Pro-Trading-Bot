from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MarketContext:
    """
    Shared context between all ICT engines.

    Every engine reads from and writes to this object.
    It is the single source of truth for the entire system.
    """

    # ==========================================================
    # RAW DATA
    # ==========================================================

    candles: Any = None

    # ==========================================================
    # SWINGS
    # ==========================================================

    swings: list = field(default_factory=list)

    # ==========================================================
    # MARKET STRUCTURE
    # ==========================================================

    structure: list = field(default_factory=list)

    # ==========================================================
    # TREND
    # ==========================================================

    trend: str = "UNKNOWN"

    previous_trend: str = "UNKNOWN"

    # ==========================================================
    # EXTERNAL STRUCTURE
    # ==========================================================

    external_high: Optional[float] = None
    external_low: Optional[float] = None

    external_high_index: Optional[int] = None
    external_low_index: Optional[int] = None

    # ==========================================================
    # INTERNAL STRUCTURE
    # ==========================================================

    internal_highs: list = field(default_factory=list)
    internal_lows: list = field(default_factory=list)

    # ==========================================================
    # BOS / CHOCH
    # ==========================================================

    bos: list = field(default_factory=list)

    choch: list = field(default_factory=list)

    # ==========================================================
    # LIQUIDITY
    # ==========================================================

    liquidity: list = field(default_factory=list)

    liquidity_sweeps: list = field(default_factory=list)

    # ==========================================================
    # FAIR VALUE GAPS
    # ==========================================================

    fvgs: list = field(default_factory=list)

    # ==========================================================
    # ORDER BLOCKS
    # ==========================================================

    order_blocks: list = field(default_factory=list)

    # ==========================================================
    # BREAKER BLOCKS
    # ==========================================================

    breaker_blocks: list = field(default_factory=list)

    # ==========================================================
    # PREMIUM / DISCOUNT
    # ==========================================================

    dealing_range_high: Optional[float] = None

    dealing_range_low: Optional[float] = None

    equilibrium: Optional[float] = None

    premium_zone = None

    discount_zone = None

    current_price: Optional[float] = None

    current_price_zone: str = "UNKNOWN"

    premium = None

    discount = None

    # ==========================================================
    # OTE
    # ==========================================================

    ote = None

    ote_direction: str = "NONE"

    ote_lower_bound: Optional[float] = None

    ote_upper_bound: Optional[float] = None

    ote_level_62: Optional[float] = None

    ote_level_705: Optional[float] = None

    ote_level_79: Optional[float] = None

    in_ote_zone: bool = False

    # ==========================================================
    # SETUP
    # ==========================================================

    setups: list = field(default_factory=list)

    active_setup = None

    setup_bias: str = "NONE"

    setup_score: int = 0

    setup_status: str = "INVALID"

    setup_blockers: list = field(default_factory=list)

    # ==========================================================
    # ENTRY
    # ==========================================================

    entry_trigger: Any = None

    entry_status: str = "NOT_CONFIRMED"

    entry_direction: str = "NONE"

    entry_trigger_type: str = "NONE"

    entry_confirmed: bool = False

    entry_blockers: list = field(default_factory=list)

    entry = None

    # ==========================================================
    # TRADE PLAN
    # ==========================================================

    trade_plan: Any = None

    trade_plan_status: str = "NO_TRADE"

    trade_direction: str = "NONE"

    planned_entry_price: Optional[float] = None

    planned_stop_loss: Optional[float] = None

    planned_take_profit: Optional[float] = None

    planned_risk: Optional[float] = None

    planned_reward: Optional[float] = None

    planned_risk_reward: Optional[float] = None

    trade_plan_blockers: list = field(default_factory=list)

    stop_loss = None

    take_profit = None

    risk_reward = None

    # ==========================================================
    # DEBUG
    # ==========================================================

    debug: dict = field(default_factory=dict)
