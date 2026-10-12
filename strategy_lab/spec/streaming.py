"""Bar-by-bar indicator runtimes for the generic NautilusTrader strategy.

Each spec indicator becomes a runtime with ``update(bar)``, ``initialized`` and ``outputs()``. Where
NautilusTrader has the indicator we drive the Nautilus class (with the options chosen in LEARNINGS.md §8);
ADX, OBV and highest/lowest are implemented here. The fast engine (``engines/fast/indicators.py``) reproduces
these exact recurrences and warm-ups; ``tests/test_indicators.py`` checks both against reference formulas.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    CommodityChannelIndex,
    DonchianChannel,
    ExponentialMovingAverage,
    HullMovingAverage,
    KeltnerChannel,
    MovingAverageConvergenceDivergence,
    MovingAverageType,
    RateOfChange,
    RelativeStrengthIndex,
    SimpleMovingAverage,
    Stochastics,
    VolumeWeightedAveragePrice,
    WeightedMovingAverage,
    WilderMovingAverage,
)

from strategy_lab.spec.indicators import resolved_params, resolved_source
from strategy_lab.spec.schema import Indicator


@dataclass(frozen=True)
class BarValues:
    open_time: datetime  # UTC, bar open
    open: float
    high: float
    low: float
    close: float
    volume: float

    def field(self, name: str) -> float:
        match name:
            case "hl2":
                return (self.high + self.low) / 2.0
            case "hlc3":
                return (self.high + self.low + self.close) / 3.0
            case "ohlc4":
                return (self.open + self.high + self.low + self.close) / 4.0
            case _:
                value: float = getattr(self, name)
                return value


class Runtime(Protocol):
    @property
    def initialized(self) -> bool: ...

    def update(self, bar: BarValues) -> None: ...

    def outputs(self) -> dict[str, float]: ...


class _SourceMA:
    """SMA / EMA / WMA / HMA / ROC / RSI on a single source value."""

    def __init__(self, indicator: object, source: str, scale: float = 1.0) -> None:
        self._ind = indicator
        self._source = source
        self._scale = scale

    @property
    def initialized(self) -> bool:
        return bool(self._ind.initialized)  # type: ignore[attr-defined]

    def update(self, bar: BarValues) -> None:
        self._ind.update_raw(bar.field(self._source))  # type: ignore[attr-defined]

    def outputs(self) -> dict[str, float]:
        return {"value": float(self._ind.value) * self._scale}  # type: ignore[attr-defined]


class _Macd:
    def __init__(self, fast: int, slow: int, signal: int, source: str) -> None:
        self._macd = MovingAverageConvergenceDivergence(fast, slow, MovingAverageType.EXPONENTIAL)
        self._signal = ExponentialMovingAverage(signal)
        self._source = source

    @property
    def initialized(self) -> bool:
        return bool(self._signal.initialized)

    def update(self, bar: BarValues) -> None:
        self._macd.update_raw(bar.field(self._source))
        if self._macd.initialized:  # the signal line starts once the MACD line is valid
            self._signal.update_raw(self._macd.value)

    def outputs(self) -> dict[str, float]:
        line, signal = float(self._macd.value), float(self._signal.value)
        return {"line": line, "signal": signal, "hist": line - signal}


class _Bollinger:
    def __init__(self, period: int, std: float, source: str) -> None:
        self._bb = BollingerBands(period, std)
        self._source = source

    @property
    def initialized(self) -> bool:
        return bool(self._bb.initialized)

    def update(self, bar: BarValues) -> None:
        value = bar.field(self._source)
        self._bb.update_raw(value, value, value)  # typical price of (v, v, v) is v: bands on the chosen source

    def outputs(self) -> dict[str, float]:
        upper, middle, lower = float(self._bb.upper), float(self._bb.middle), float(self._bb.lower)
        width = (upper - lower) / middle if middle else math.nan
        return {"middle": middle, "upper": upper, "lower": lower, "width": width}


class _HLC:
    """Indicators fed with (high, low, close): ATR, CCI, Keltner, Stochastics."""

    def __init__(self, indicator: object, outputs: dict[str, str]) -> None:
        self._ind = indicator
        self._outputs = outputs  # our output name -> Nautilus attribute

    @property
    def initialized(self) -> bool:
        return bool(self._ind.initialized)  # type: ignore[attr-defined]

    def update(self, bar: BarValues) -> None:
        self._ind.update_raw(bar.high, bar.low, bar.close)  # type: ignore[attr-defined]

    def outputs(self) -> dict[str, float]:
        return {name: float(getattr(self._ind, attr)) for name, attr in self._outputs.items()}


class _Donchian:
    def __init__(self, period: int) -> None:
        self._dc = DonchianChannel(period)

    @property
    def initialized(self) -> bool:
        return bool(self._dc.initialized)

    def update(self, bar: BarValues) -> None:
        self._dc.update_raw(bar.high, bar.low)

    def outputs(self) -> dict[str, float]:
        return {"middle": float(self._dc.middle), "upper": float(self._dc.upper), "lower": float(self._dc.lower)}


class _Vwap:
    def __init__(self) -> None:
        self._vwap = VolumeWeightedAveragePrice()

    @property
    def initialized(self) -> bool:
        return bool(self._vwap.initialized)

    def update(self, bar: BarValues) -> None:
        # The bar *open* time decides the session (Nautilus's own handle_bar would use the close time and put the
        # 23:45-00:00 bar into the next day).
        self._vwap.update_raw(bar.field("hlc3"), bar.volume, bar.open_time)

    def outputs(self) -> dict[str, float]:
        return {"value": float(self._vwap.value)}


class Adx:
    """Wilder's ADX: TR, +DM, -DM smoothed with Wilder MAs (seeded with the first value, like Nautilus's
    ``WilderMovingAverage``); DX = 100·|+DI − −DI|/(+DI + −DI); ADX = Wilder MA of DX. The first bar only seeds
    the previous high/low/close. Valid once both stages are initialized (2·period bars after the seed bar)."""

    def __init__(self, period: int) -> None:
        self._tr = WilderMovingAverage(period)
        self._plus = WilderMovingAverage(period)
        self._minus = WilderMovingAverage(period)
        self._adx = WilderMovingAverage(period)
        self._prev: tuple[float, float, float] | None = None
        self._plus_di = self._minus_di = 0.0

    @property
    def initialized(self) -> bool:
        return bool(self._adx.initialized)

    def update(self, bar: BarValues) -> None:
        if self._prev is None:
            self._prev = (bar.high, bar.low, bar.close)
            return
        prev_high, prev_low, prev_close = self._prev
        up, down = bar.high - prev_high, prev_low - bar.low
        plus_dm = up if (up > down and up > 0.0) else 0.0
        minus_dm = down if (down > up and down > 0.0) else 0.0
        tr = max(bar.high, prev_close) - min(bar.low, prev_close)
        self._tr.update_raw(tr)
        self._plus.update_raw(plus_dm)
        self._minus.update_raw(minus_dm)
        self._prev = (bar.high, bar.low, bar.close)
        if not self._tr.initialized:
            return
        atr = self._tr.value
        self._plus_di = 100.0 * self._plus.value / atr if atr > 0.0 else 0.0
        self._minus_di = 100.0 * self._minus.value / atr if atr > 0.0 else 0.0
        total = self._plus_di + self._minus_di
        self._adx.update_raw(100.0 * abs(self._plus_di - self._minus_di) / total if total > 0.0 else 0.0)

    def outputs(self) -> dict[str, float]:
        return {"adx": float(self._adx.value), "plus_di": self._plus_di, "minus_di": self._minus_di}


class Obv:
    """Textbook OBV: add volume when the close is above the previous close, subtract when below."""

    def __init__(self) -> None:
        self._prev_close: float | None = None
        self._value = 0.0

    @property
    def initialized(self) -> bool:
        return self._prev_close is not None

    def update(self, bar: BarValues) -> None:
        if self._prev_close is not None:
            if bar.close > self._prev_close:
                self._value += bar.volume
            elif bar.close < self._prev_close:
                self._value -= bar.volume
        self._prev_close = bar.close

    def outputs(self) -> dict[str, float]:
        return {"value": self._value}


class Extreme:
    """Highest (or lowest) of ``source`` over the last ``period`` bars, including the current bar."""

    def __init__(self, period: int, source: str, highest: bool) -> None:
        self._values: deque[float] = deque(maxlen=period)
        self._source = source
        self._highest = highest

    @property
    def initialized(self) -> bool:
        return len(self._values) == self._values.maxlen

    def update(self, bar: BarValues) -> None:
        self._values.append(bar.field(self._source))

    def outputs(self) -> dict[str, float]:
        return {"value": max(self._values) if self._highest else min(self._values)}


def make_runtime(ind: Indicator) -> Runtime:
    p = resolved_params(ind.type, ind.params)
    source = resolved_source(ind.type, ind.source) or "close"
    period = int(p.get("period", 0))
    match ind.type:
        case "sma":
            return _SourceMA(SimpleMovingAverage(period), source)
        case "ema":
            return _SourceMA(ExponentialMovingAverage(period), source)
        case "wma":
            weights = [float(w) for w in range(1, period + 1)]  # without weights Nautilus's WMA is a plain mean
            return _SourceMA(WeightedMovingAverage(period, weights=weights), source)
        case "hma":
            return _SourceMA(HullMovingAverage(period), source)
        case "rsi":
            return _SourceMA(RelativeStrengthIndex(period, MovingAverageType.WILDER), source, scale=100.0)
        case "roc":
            return _SourceMA(RateOfChange(period + 1), source, scale=100.0)
        case "macd":
            return _Macd(int(p["fast"]), int(p["slow"]), int(p["signal"]), source)
        case "bbands":
            return _Bollinger(period, p["std"], source)
        case "atr":
            return _HLC(AverageTrueRange(period, MovingAverageType.WILDER), {"value": "value"})
        case "cci":
            return _HLC(CommodityChannelIndex(period), {"value": "value"})
        case "keltner":
            kc = KeltnerChannel(period, p["multiplier"], MovingAverageType.EXPONENTIAL, MovingAverageType.WILDER)
            return _HLC(kc, {"middle": "middle", "upper": "upper", "lower": "lower"})
        case "stoch":
            stoch = Stochastics(
                int(p["k_period"]),
                int(p["d_period"]),
                int(p["smooth"]),
                MovingAverageType.SIMPLE,
                "moving_average",
            )
            return _HLC(stoch, {"k": "value_k", "d": "value_d"})
        case "donchian":
            return _Donchian(period)
        case "vwap":
            return _Vwap()
        case "adx":
            return Adx(period)
        case "obv":
            return Obv()
        case "highest":
            return Extreme(period, source, highest=True)
        case "lowest":
            return Extreme(period, source, highest=False)
    raise ValueError(f"no runtime for indicator type {ind.type!r}")
