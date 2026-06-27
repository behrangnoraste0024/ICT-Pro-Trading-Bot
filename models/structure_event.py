from dataclasses import dataclass

@dataclass
class StructureEvent:
    type: str
    direction: str
    price: float
    index: int