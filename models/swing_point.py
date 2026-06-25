from dataclasses import dataclass


@dataclass
class SwingPoint:
    index: int
    price: float
    swing_type: str

    label: str = "UNKNOWN"

    broken: bool = False
    bos: bool = False
    choch: bool = False

    def __str__(self):
        return (
            f"{self.swing_type} | "
            f"{self.label} | "
            f"{self.price} | "
            f"BOS={self.bos}"
        )