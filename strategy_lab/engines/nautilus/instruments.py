"""BTC-PERP and XAU-PERP perpetuals on a simulated venue named LIGHTER.

Contract specs come from Lighter's ``orderBookDetails`` (saved by ``make data`` to
``data/raw/lighter/order_book_details.json``) when that file exists. Lighter's API is blocked from the build
sandbox, so the defaults below are used there; they are documented in DATA.md and every result records which
spec was used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from nautilus_trader.model.currencies import BTC, USDC
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Currency, Price, Quantity

from strategy_lab import config
from strategy_lab.data.sources.lighter import parse_market_spec

VENUE = Venue("LIGHTER")
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


def instrument_id(symbol: MarketSymbol) -> InstrumentId:
    return InstrumentId(Symbol(symbol), VENUE)


def make_instrument(symbol: MarketSymbol, maker_fee: float, taker_fee: float) -> CryptoPerpetual:
    """A linear USDC-settled perpetual.

    ``margin_init=1`` because Nautilus's default *leveraged* margin model computes initial margin as
    ``notional / leverage * margin_init`` (accounting/margin_models.pyx), so the account leverage alone decides
    the margin. Fees are fractions (0.00028 = 2.8 bps) and are applied by ``MakerTakerFeeModel``.
    """
    spec = contract_spec(symbol)
    base = BTC if spec.base == "BTC" else Currency.from_str(spec.base)
    return CryptoPerpetual(
        instrument_id=instrument_id(symbol),
        raw_symbol=Symbol(spec.base),
        base_currency=base,
        quote_currency=USDC,
        settlement_currency=USDC,
        is_inverse=False,
        price_precision=spec.price_decimals,
        size_precision=spec.size_decimals,
        price_increment=Price(spec.tick_size, spec.price_decimals),
        size_increment=Quantity(spec.size_increment, spec.size_decimals),
        min_quantity=Quantity(spec.min_quantity, spec.size_decimals),
        margin_init=Decimal(1),
        margin_maint=Decimal("0.5"),
        maker_fee=Decimal(str(maker_fee)),
        taker_fee=Decimal(str(taker_fee)),
        ts_event=0,
        ts_init=0,
    )
