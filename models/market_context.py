from dataclasses import dataclass, field


@dataclass
class MarketContext:

    # -----------------------------
    # Raw Data
    # -----------------------------

    candles = None

    swings: list = field(default_factory=list)

    # -----------------------------
    # Trend
    # -----------------------------

    trend: str = "UNKNOWN"

    # -----------------------------
    # External Structure
    # -----------------------------

    external_high: float | None = None
    external_low: float | None = None

    # -----------------------------
    # Internal Structure
    # -----------------------------

    internal_highs: list = field(default_factory=list)
    internal_lows: list = field(default_factory=list)

    # -----------------------------
    # Smart Money Events
    # -----------------------------

    bos: list = field(default_factory=list)
    choch: list = field(default_factory=list)

    liquidity: list = field(default_factory=list)

    fvgs: list = field(default_factory=list)

    order_blocks: list = field(default_factory=list)

    # -----------------------------
    # Future Modules
    # -----------------------------

    premium_discount = None

    ote = None

    entry = None

    risk = None