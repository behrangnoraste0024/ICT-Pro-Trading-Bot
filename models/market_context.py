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

    premium = None

    discount = None

    equilibrium = None

    # ==========================================================
    # OTE
    # ==========================================================

    ote = None

    # ==========================================================
    # ENTRY
    # ==========================================================

    entry = None

    stop_loss = None

    take_profit = None

    risk_reward = None

    # ==========================================================
    # DEBUG
    # ==========================================================

    debug: dict = field(default_factory=dict)
