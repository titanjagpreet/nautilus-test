"""The simulated LIGHTER venue: margin account, netting, leverage, maker/taker fees, slippage, funding."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import LatencyModel, MakerTakerFeeModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money

from strategy_lab.costs import fee_profile
from strategy_lab.engines.contracts import MarketSymbol
from strategy_lab.engines.nautilus.fill_model import MarketAndStopSlippageFillModel
from strategy_lab.engines.nautilus.funding import FundingModule
from strategy_lab.engines.nautilus.instruments import VENUE, make_instrument


@dataclass(frozen=True)
class VenueSettings:
    leverage: float = 3.0
    starting_balance: float = 10_000.0
    fee_profile: str = "lighter_standard"
    slippage_ticks: int = 1
    adaptive_bar_ordering: bool = True
    # 1 ns latency makes orders sent at a bar close reach the venue after the next data point (spec engine).
    latency_ns: int = 0


def new_engine(log_level: str = "ERROR") -> BacktestEngine:
    return BacktestEngine(
        BacktestEngineConfig(trader_id="BACKTESTER-001", logging=LoggingConfig(log_level=log_level))
    )


def add_lighter_venue(
    engine: BacktestEngine,
    symbol: MarketSymbol,
    settings: VenueSettings,
    funding: pd.DataFrame | None,
) -> tuple[CryptoPerpetual, FundingModule | None]:
    """Add the LIGHTER venue with one perpetual. Returns (instrument, funding module or None)."""
    fees = fee_profile(settings.fee_profile)
    instrument = make_instrument(symbol, maker_fee=fees.maker_rate, taker_fee=fees.taker_rate)
    module = FundingModule(instrument.id, funding) if funding is not None and not funding.empty else None
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(settings.starting_balance, USDC)],
        base_currency=USDC,
        default_leverage=Decimal(str(settings.leverage)),
        modules=[module] if module is not None else None,
        fill_model=MarketAndStopSlippageFillModel(settings.slippage_ticks),
        fee_model=MakerTakerFeeModel(),
        latency_model=LatencyModel(base_latency_nanos=settings.latency_ns) if settings.latency_ns else None,
        bar_adaptive_high_low_ordering=settings.adaptive_bar_ordering,
        reject_stop_orders=False,  # a stop already through the market fills at market instead of being rejected
    )
    engine.add_instrument(instrument)
    return instrument, module
