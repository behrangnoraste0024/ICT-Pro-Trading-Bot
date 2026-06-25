from dataclasses import dataclass, field


@dataclass
class MarketContext:

    candles = None

    swings: list = field(default_factory=list)

    trend: str = "UNKNOWN"

    bos: list = field(default_factory=list)

    choch: list = field(default_factory=list)

    liquidity: list = field(default_factory=list)

    fvgs: list = field(default_factory=list)

    order_blocks: list = field(default_factory=list)

    external_high: float | None = None
    external_low: float | None = None