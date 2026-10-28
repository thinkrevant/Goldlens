"""Contract specifications and default cost assumptions.

Specs follow the Hack in Hills '26 PS 03 problem statement (MCX). Cost defaults are
approximate retail figures and are editable in the dashboard.
"""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PANEL_PATH = DATA_DIR / "gold_futures.parquet"
BRIEF_CACHE_DIR = DATA_DIR / "briefs"

# Every price is converted to rupees per 10 g of 999-purity gold.
BASE_GRAMS = 10.0
BASE_PURITY = 999.0


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    lot_grams: float      # grams of gold per lot
    quote_grams: float    # the price is quoted per this many grams
    purity: float         # fineness, parts per 1000
    expiry_window: str    # expiry day-of-month window, from the PS
    tick: float           # minimum price move in quoted rupees

    @property
    def to_base(self) -> float:
        """Multiplier that turns a quoted price into Rs per 10 g of 999 gold."""
        return (BASE_GRAMS / self.quote_grams) * (BASE_PURITY / self.purity)

    @property
    def rupees_per_point(self) -> float:
        """Rupee P&L per lot for a 1-rupee move in the quoted price."""
        return self.lot_grams / self.quote_grams


SPECS: dict[str, ContractSpec] = {
    "GOLDM": ContractSpec("GOLDM", 100, 10, 995, "3rd-5th", 1.0),
    "GOLDTEN": ContractSpec("GOLDTEN", 10, 10, 999, "27th-31st", 1.0),
    "GOLDGUINEA": ContractSpec("GOLDGUINEA", 8, 8, 999, "27th-31st", 1.0),
    "GOLDPETAL": ContractSpec("GOLDPETAL", 1, 1, 999, "27th-31st", 1.0),
}
SYMBOLS = list(SPECS)

# Pairs scanned for relative value. 200 g is the smallest size every lot divides.
PAIRS = [
    ("GOLDTEN", "GOLDGUINEA"),
    ("GOLDTEN", "GOLDPETAL"),
    ("GOLDGUINEA", "GOLDPETAL"),
    ("GOLDM", "GOLDTEN"),
    ("GOLDM", "GOLDGUINEA"),
    ("GOLDM", "GOLDPETAL"),
]
LEG_GRAMS = 200.0


@dataclass
class CostModel:
    """Per-trade costs. Rates are fractions of traded notional."""
    brokerage_per_order: float = 20.0       # Rs, flat discount-broker fee per leg order
    exchange_rate: float = 0.000021         # MCX transaction charge, ~Rs 2.1 per lakh
    sebi_rate: float = 0.000001             # SEBI turnover fee, Rs 10 per crore
    ctt_rate: float = 0.0001                # commodity transaction tax, sell side
    stamp_rate: float = 0.00002             # stamp duty, buy side
    gst_rate: float = 0.18                  # on brokerage + exchange + SEBI fees
    slippage_ticks: float = 2.0             # ticks lost per lot per fill vs settlement

    def leg_cost(self, spec: ContractSpec, price: float, lots: float, side: int) -> float:
        """Rupee cost of one fill. side=+1 buy, -1 sell."""
        if lots == 0:
            return 0.0
        notional = abs(lots) * price * spec.rupees_per_point
        brokerage = self.brokerage_per_order
        exchange = notional * self.exchange_rate
        sebi = notional * self.sebi_rate
        tax = notional * (self.ctt_rate if side < 0 else self.stamp_rate)
        gst = (brokerage + exchange + sebi) * self.gst_rate
        slippage = abs(lots) * self.slippage_ticks * spec.tick * spec.rupees_per_point
        return brokerage + exchange + sebi + tax + gst + slippage

    @classmethod
    def zero(cls) -> "CostModel":
        return cls(0, 0, 0, 0, 0, 0, 0)
