"""Every catalogue indicator vs an independent reference calculation.

Input: a synthetic random-walk OHLCV series generated here (labelled synthetic; never used as results). The
runtimes under test are the ones the NautilusTrader strategy uses (Nautilus classes where they exist, our own
otherwise); references are written with pandas/NumPy from the definitions in LEARNINGS.md §8.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from strategy_lab.spec.indicators import CATALOGUE
from strategy_lab.spec.schema import Indicator
from strategy_lab.spec.streaming import BarValues, make_runtime

N = 600


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, N)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.001, N))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.002, N)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.002, N)))
    volume = rng.uniform(1.0, 50.0, N)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=15 * i) for i in range(N)]
    return pd.DataFrame({"time": times, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def run(df: pd.DataFrame, ind: Indicator) -> pd.DataFrame:
    """Feed bars one by one; NaN while not initialized."""
    runtime = make_runtime(ind)
    rows = []
    for r in df.itertuples():
        runtime.update(BarValues(r.time, r.open, r.high, r.low, r.close, r.volume))
        rows.append(runtime.outputs() if runtime.initialized else {})
    return pd.DataFrame(rows, columns=list(CATALOGUE[ind.type].outputs), dtype=float)


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False).mean()  # y0 = x0, then α = 2/(n+1)


def wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1.0 / n, adjust=False).mean()  # y0 = x0, then α = 1/n


def wma(x: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n).apply(lambda a: float(np.dot(a, w) / w.sum()), raw=True)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1).fillna(df["close"])
    return np.maximum(df["high"], prev) - np.minimum(df["low"], prev)


def check(actual: pd.Series, expected: pd.Series, first_valid: int) -> None:
    a, e = actual.to_numpy(), expected.to_numpy()
    assert np.isnan(a[: first_valid]).all(), "value published before warm-up ended"
    np.testing.assert_allclose(a[first_valid:], e[first_valid:], rtol=1e-9, atol=1e-9)


def test_sma_ema_wma(ohlcv: pd.DataFrame) -> None:
    c = ohlcv["close"]
    check(run(ohlcv, Indicator(id="x", type="sma", params={"period": 20}))["value"], c.rolling(20).mean(), 19)
    check(run(ohlcv, Indicator(id="x", type="ema", params={"period": 20}))["value"], ema(c, 20), 19)
    check(run(ohlcv, Indicator(id="x", type="wma", params={"period": 20}))["value"], wma(c, 20), 19)


def test_hma(ohlcv: pd.DataFrame) -> None:
    c, n = ohlcv["close"], 21
    raw = 2 * wma(c, n // 2) - wma(c, n)
    expected = wma(raw, int(math.sqrt(n)))
    out = run(ohlcv, Indicator(id="x", type="hma", params={"period": n}))["value"]
    # Nautilus starts the outer WMA on partial-window inner values; compare once every input is full-window.
    first_full = n - 1 + int(math.sqrt(n)) - 1
    np.testing.assert_allclose(out[first_full:], expected[first_full:], rtol=1e-9)
    assert out[: n - 1].isna().all()


def test_rsi_wilder_and_textbook_convergence(ohlcv: pd.DataFrame) -> None:
    c, n = ohlcv["close"], 14
    diff = c.diff().fillna(0.0)  # Nautilus feeds a 0 change on the first bar
    gain, loss = wilder(diff.clip(lower=0), n), wilder((-diff).clip(lower=0), n)
    expected = 100 - 100 / (1 + gain / loss)
    out = run(ohlcv, Indicator(id="x", type="rsi", params={"period": n}))["value"]
    check(out, expected, n - 1)
    # Textbook Wilder seeds with the SMA of the first n changes; after ~10n bars the two agree closely.
    d = c.diff()
    g, lo = d.clip(lower=0), (-d).clip(lower=0)
    avg_g, avg_l = [g.iloc[1 : n + 1].mean()], [lo.iloc[1 : n + 1].mean()]
    for i in range(n + 1, len(c)):
        avg_g.append((avg_g[-1] * (n - 1) + g.iloc[i]) / n)
        avg_l.append((avg_l[-1] * (n - 1) + lo.iloc[i]) / n)
    textbook = 100 - 100 / (1 + np.array(avg_g) / np.array(avg_l))
    assert abs(out.iloc[-1] - textbook[-1]) < 0.01


def test_macd(ohlcv: pd.DataFrame) -> None:
    c = ohlcv["close"]
    line = ema(c, 12) - ema(c, 26)
    signal = pd.Series(np.nan, index=c.index)
    signal.iloc[25:] = ema(line.iloc[25:], 9).to_numpy()  # the signal EMA starts when the line is valid
    out = run(ohlcv, Indicator(id="x", type="macd", params={"fast": 12, "slow": 26, "signal": 9}))
    first = 25 + 9 - 1
    check(out["line"], line, first)
    check(out["signal"], signal, first)
    check(out["hist"], line - signal, first)


def test_bollinger(ohlcv: pd.DataFrame) -> None:
    c = ohlcv["close"]
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    out = run(ohlcv, Indicator(id="x", type="bbands", params={"period": 20, "std": 2.0}))
    check(out["middle"], mid, 19)
    check(out["upper"], mid + 2 * sd, 19)
    check(out["lower"], mid - 2 * sd, 19)
    check(out["width"], 4 * sd / mid, 19)


def test_atr_and_keltner(ohlcv: pd.DataFrame) -> None:
    atr = wilder(true_range(ohlcv), 14)
    check(run(ohlcv, Indicator(id="x", type="atr", params={"period": 14}))["value"], atr, 13)
    tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    mid, atr20 = ema(tp, 20), wilder(true_range(ohlcv), 20)
    out = run(ohlcv, Indicator(id="x", type="keltner", params={"period": 20, "multiplier": 1.5}))
    check(out["middle"], mid, 19)
    check(out["upper"], mid + 1.5 * atr20, 19)
    check(out["lower"], mid - 1.5 * atr20, 19)


def test_stochastics(ohlcv: pd.DataFrame) -> None:
    hh = ohlcv["high"].rolling(14, min_periods=1).max()
    ll = ohlcv["low"].rolling(14, min_periods=1).min()
    raw_k = 100 * (ohlcv["close"] - ll) / (hh - ll)
    k = raw_k.rolling(3, min_periods=1).mean()  # Nautilus SMA averages what it has during warm-up
    d = k.rolling(3, min_periods=1).mean()
    out = run(ohlcv, Indicator(id="x", type="stoch", params={"k_period": 14, "d_period": 3, "smooth": 3}))
    check(out["k"], k, 13)
    check(out["d"], d, 13)


def test_adx(ohlcv: pd.DataFrame) -> None:
    n = 14
    h, lo, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    up, down = h.diff(), -lo.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)[1:]
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)[1:]
    tr = (np.maximum(h, c.shift(1)) - np.minimum(lo, c.shift(1))).to_numpy()[1:]
    atr, pdm, mdm = (wilder(pd.Series(x), n).to_numpy() for x in (tr, plus_dm, minus_dm))
    plus_di, minus_di = 100 * pdm / atr, 100 * mdm / atr
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = wilder(pd.Series(dx[n - 1 :]), n).to_numpy()  # DX exists once the DI smoothing is initialized
    expected = np.full(len(c), np.nan)
    expected[n : n + len(adx)] = adx
    out = run(ohlcv, Indicator(id="x", type="adx", params={"period": n}))
    first = 2 * n - 1
    check(out["adx"], pd.Series(expected), first)
    np.testing.assert_allclose(out["plus_di"][first:], plus_di[first - 1 :], rtol=1e-9)
    np.testing.assert_allclose(out["minus_di"][first:], minus_di[first - 1 :], rtol=1e-9)


def test_donchian_highest_lowest(ohlcv: pd.DataFrame) -> None:
    hi, lo = ohlcv["high"].rolling(20).max(), ohlcv["low"].rolling(20).min()
    out = run(ohlcv, Indicator(id="x", type="donchian", params={"period": 20}))
    check(out["upper"], hi, 19)
    check(out["lower"], lo, 19)
    check(out["middle"], (hi + lo) / 2, 19)
    check(run(ohlcv, Indicator(id="x", type="highest", params={"period": 20}))["value"], hi, 19)
    check(run(ohlcv, Indicator(id="x", type="lowest", params={"period": 20}))["value"], lo, 19)
    closes = run(ohlcv, Indicator(id="x", type="highest", params={"period": 5}, source="close"))["value"]
    check(closes, ohlcv["close"].rolling(5).max(), 4)


def test_roc_cci_obv(ohlcv: pd.DataFrame) -> None:
    c = ohlcv["close"]
    check(run(ohlcv, Indicator(id="x", type="roc", params={"period": 10}))["value"], 100 * (c / c.shift(10) - 1), 10)
    tp = (ohlcv["high"] + ohlcv["low"] + c) / 3
    sma = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda a: np.mean(np.abs(a - a.mean())), raw=True)
    check(run(ohlcv, Indicator(id="x", type="cci", params={"period": 20}))["value"], (tp - sma) / (0.015 * mad), 19)
    obv = (np.sign(c.diff().fillna(0.0)) * ohlcv["volume"]).cumsum()
    check(run(ohlcv, Indicator(id="x", type="obv"))["value"], obv, 0)


def test_vwap_resets_each_utc_day(ohlcv: pd.DataFrame) -> None:
    tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    day = pd.Series([t.date() for t in ohlcv["time"]])
    pv = (tp * ohlcv["volume"]).groupby(day).cumsum()
    v = ohlcv["volume"].groupby(day).cumsum()
    check(run(ohlcv, Indicator(id="x", type="vwap"))["value"], pv / v, 0)


def test_every_catalogue_type_is_covered() -> None:
    tested = {"sma", "ema", "wma", "hma", "rsi", "macd", "bbands", "atr", "keltner", "stoch", "adx", "donchian",
              "highest", "lowest", "roc", "cci", "obv", "vwap"}  # fmt: skip
    assert tested == set(CATALOGUE)
