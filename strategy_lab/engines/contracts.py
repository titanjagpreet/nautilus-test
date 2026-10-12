"""Contract specs for the simulated LIGHTER perpetuals — shared by both engines (no NautilusTrader import).

Specs come from Lighter's ``orderBookDetails`` (saved by ``make data`` to
``data/raw/lighter/order_book_details.json``) when that file exists. Lighter's API is blocked from the build
sandbox, so the defaults below are used there; they are documented in DATA.md and every result records which
spec was used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from strategy_lab import config
from strategy_lab.data.sources.lighter import parse_market_spec

MarketSymbol = Literal["BTC-PERP", "XAU-PERP"]


@dataclass(frozen=True)
class ContractSpec:
    symbol: MarketSymbol
    base: str
    price_decimals: int
    size_decimals: int
    min_quantity: float
    origin: str  # "lighter_metadata" or "default"

    @property
    def tick_size(self) -> float:
        return 10.0**-self.price_decimals

    @property
    def size_increment(self) -> float:
        return 10.0**-self.size_decimals


# Used only when Lighter metadata is unavailable. BTC: 0.1 USDC tick, 0.00001 BTC lot (typical for BTC perps
# quoted in USD). XAU: 0.01 USDC tick, 0.001 oz lot.
DEFAULT_SPECS: dict[str, ContractSpec] = {
    "BTC-PERP": ContractSpec("BTC-PERP", "BTC", 1, 5, 0.0002, "default"),
    "XAU-PERP": ContractSpec("XAU-PERP", "XAU", 2, 3, 0.001, "default"),
}


def contract_spec(symbol: MarketSymbol) -> ContractSpec:
    path = config.raw_dir() / "lighter" / "order_book_details.json"
    default = DEFAULT_SPECS[symbol]
    if not path.exists():
        return default
    details = json.loads(path.read_text()).get("order_book_details", [])
    market = parse_market_spec(details, default.base)
    return ContractSpec(
        symbol,
        default.base,
        market.price_decimals,
        market.size_decimals,
        market.min_base_amount,
        "lighter_metadata",
    )
