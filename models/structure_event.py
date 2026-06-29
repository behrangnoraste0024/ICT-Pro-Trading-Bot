from dataclasses import dataclass


@dataclass
class StructureEvent:
    """
    Represents one structural point in the market.

    Every swing becomes one StructureEvent and
    all ICT engines will work with this object.
    """

    # --------------------------
    # Swing Info
    # --------------------------

    index: int
    price: float
    swing_type: str        # HIGH / LOW

    # --------------------------
    # Structure
    # --------------------------

    label: str = ""        # HH HL LH LL

    # --------------------------
    # External / Internal
    # --------------------------

    is_external: bool = False
    is_internal: bool = False

    # --------------------------
    # Smart Money Events
    # --------------------------

    bos: bool = False
    choch: bool = False

    broken: bool = False

    swept: bool = False

    # --------------------------
    # Trend
    # --------------------------

    trend_before: str = ""
    trend_after: str = ""

    # --------------------------
    # Liquidity
    # --------------------------

    liquidity: bool = False

    liquidity_type: str = ""

    # --------------------------
    # Order Block
    # --------------------------

    order_block: bool = False

    # --------------------------
    # Fair Value Gap
    # --------------------------

    fvg: bool = False

    def __str__(self):

        txt = f"{self.swing_type} | {self.label} | {self.price}"

        if self.bos:
            txt += " | BOS"

        if self.choch:
            txt += " | CHOCH"

        if self.swept:
            txt += " | SWEEP"

        return txt