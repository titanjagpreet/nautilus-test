"""BTC-PERP and XAU-PERP perpetuals on a simulated venue named LIGHTER (specs: ``engines/contracts.py``)."""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.currencies import BTC, USDC
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Currency, Price, Quantity

from strategy_lab.engines.contracts import MarketSymbol, contract_spec

VENUE = Venue("LIGHTER")


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
