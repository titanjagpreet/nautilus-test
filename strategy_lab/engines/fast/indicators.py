"""Numba indicators that reproduce the bar-by-bar runtimes (``spec/streaming.py``) exactly.

Each function takes float64 arrays and returns arrays with ``NaN`` wherever the streaming indicator is not yet
initialized. To be *bit-identical* with NautilusTrader the operation order is copied too: Nautilus means are
sequential sums (``core/stats.pyx``), its weighted averages go through ``np.average`` (NumPy pairwise
summation, re-implemented in ``_pairwise_sum``), and EMAs apply ``α·x + (1-α)·prev`` even on the seed bar.
"""

from __future__ import annotations

import math

import numba as nb
import numpy as np
import numpy.typing as npt

F64 = npt.NDArray[np.float64]
NAN = math.nan


@nb.njit(cache=True)
def _pairwise_block(a: F64, start: int, n: int) -> float:
    """The base case of NumPy's ``pairwise_sum`` (n <= 128): unrolled by 8 below n, plain loop below 8."""
    if n < 8:
        res: float = -0.0
        for i in range(start, start + n):
            res += a[i]
        return res
    r0, r1, r2, r3 = a[start], a[start + 1], a[start + 2], a[start + 3]
    r4, r5, r6, r7 = a[start + 4], a[start + 5], a[start + 6], a[start + 7]
    i = 8
    while i < n - (n % 8):
        r0 += a[start + i]
        r1 += a[start + i + 1]
        r2 += a[start + i + 2]
        r3 += a[start + i + 3]
        r4 += a[start + i + 4]
        r5 += a[start + i + 5]
        r6 += a[start + i + 6]
        r7 += a[start + i + 7]
        i += 8
    res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))
    while i < n:
        res += a[start + i]
        i += 1
    return res


@nb.njit(cache=True)
def _pairwise_sum(a: F64, start: int, n: int) -> float:
    """NumPy's ``pairwise_sum`` for contiguous float64 (numpy/_core/src/umath/loops_utils.h.src).

    NumPy recurses: blocks of at most 128 are summed by ``_pairwise_block``, larger ranges split at
    ``n/2`` rounded down to a multiple of 8 and return ``left + right``. The recursion is replayed here with an
    explicit stack (same additions in the same order) because Numba's on-disk cache cannot reload a
    self-recursive function: the reloaded code segfaults (LEARNINGS §16).
    """
    if n <= 128:
        return _pairwise_block(a, start, n)
    depth = 64  # ranges halve each level: 64 levels cover any array that fits in memory
    starts, sizes, stage = np.empty(depth, np.int64), np.empty(depth, np.int64), np.zeros(depth, np.int64)
    values = np.empty(depth)
    top, n_values = 0, 0
    starts[0], sizes[0] = start, n
    while top >= 0:
        lo, size = starts[top], sizes[top]
        if size <= 128:
            values[n_values] = _pairwise_block(a, lo, size)
            n_values += 1
            top -= 1
            continue
        half = size // 2
        half -= half % 8
        if stage[top] == 0:  # left half next
            stage[top] = 1
            top += 1
            starts[top], sizes[top], stage[top] = lo, half, 0
        elif stage[top] == 1:  # then the right half
            stage[top] = 2
            top += 1
            starts[top], sizes[top], stage[top] = lo + half, size - half, 0
        else:  # both halves done: left + right
            n_values -= 1
            values[n_values - 1] = values[n_values - 1] + values[n_values]
            top -= 1
    total: float = values[0]
    return total


@nb.njit(cache=True)
def _seq_mean(x: F64, lo: int, hi: int) -> float:
    total = 0.0
    for i in range(lo, hi):
        total += x[i]
    return total / (hi - lo)


@nb.njit(cache=True)
def sma(x: F64, n: int) -> F64:
    out = np.full(len(x), NAN)
    for i in range(n - 1, len(x)):
        out[i] = _seq_mean(x, i - n + 1, i + 1)
    return out


@nb.njit(cache=True)
def _sma_partial(x: F64, n: int) -> F64:
    """SMA that averages what it has during warm-up (Nautilus's value before ``initialized``)."""
    out = np.empty(len(x))
    for i in range(len(x)):
        lo = max(0, i - n + 1)
        out[i] = _seq_mean(x, lo, i + 1)
    return out


@nb.njit(cache=True)
def _ema_values(x: F64, alpha: float) -> F64:
    out = np.empty(len(x))
    prev = 0.0
    for i in range(len(x)):
        if i == 0:
            prev = x[0]
        prev = alpha * x[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _mask_warmup(values: F64, n: int) -> F64:
    out = values.copy()
    out[: n - 1] = np.nan
    return out


def ema(x: F64, n: int) -> F64:
    return _mask_warmup(_ema_values(x, 2.0 / (n + 1.0)), n)


def wilder(x: F64, n: int) -> F64:
    return _mask_warmup(_ema_values(x, 1.0 / n), n)


@nb.njit(cache=True)
def _weighted(x: F64, weights: F64) -> F64:
    """``np.average(window, weights=weights[-len(window):])`` per bar, partial windows included."""
    n = len(weights)
    out = np.empty(len(x))
    prod = np.empty(n)
    for i in range(len(x)):
        k = min(i + 1, n)
        w0 = n - k
        for j in range(k):
            prod[j] = x[i - k + 1 + j] * weights[w0 + j]
        out[i] = _pairwise_sum(prod, 0, k) / _pairwise_sum(weights, w0, k)
    return out


def wma(x: F64, n: int) -> F64:
    return _mask_warmup(_weighted(x, np.arange(1, n + 1, dtype=np.float64)), n)


def _hull_weights(size: int) -> F64:
    w = np.arange(1, size + 1, dtype=np.float64)
    w /= w.sum()
    return w


def hma(x: F64, n: int) -> F64:
    half, root = int(n / 2), int(np.sqrt(n))
    raw = _weighted(x, _hull_weights(half)) * 2.0 - _weighted(x, _hull_weights(n))
    return _mask_warmup(_weighted(raw, _hull_weights(root)), n)


@nb.njit(cache=True)
def _rsi(x: F64, n: int) -> F64:
    alpha = 1.0 / n
    out = np.full(len(x), NAN)
    gain = loss = 0.0
    last = x[0] if len(x) else 0.0
    for i in range(len(x)):
        change = x[i] - last
        g = change if change > 0.0 else 0.0
        lo = -change if change < 0.0 else 0.0
        if i == 0:
            gain, loss = g, lo
        gain = alpha * g + (1.0 - alpha) * gain
        loss = alpha * lo + (1.0 - alpha) * loss
        last = x[i]
        if i >= n - 1:
            out[i] = 100.0 if loss == 0.0 else (1.0 - 1.0 / (1.0 + gain / loss)) * 100.0
    return out


def rsi(x: F64, n: int) -> F64:
    return _rsi(x, n)


def macd(x: F64, fast: int, slow: int, signal: int) -> tuple[F64, F64, F64]:
    line = _ema_values(x, 2.0 / (fast + 1.0)) - _ema_values(x, 2.0 / (slow + 1.0))
    sig = np.full(len(x), np.nan)
    sig[slow - 1 :] = _ema_values(line[slow - 1 :], 2.0 / (signal + 1.0))
    first = slow - 1 + signal - 1
    line_out, sig_out = line.copy(), sig.copy()
    line_out[:first] = np.nan
    sig_out[:first] = np.nan
    return line_out, sig_out, line_out - sig_out


@nb.njit(cache=True)
def _bollinger(x: F64, n: int, k: float) -> tuple[F64, F64, F64]:
    size = len(x)
    upper, middle, lower = np.full(size, NAN), np.full(size, NAN), np.full(size, NAN)
    tp = np.empty(size)
    for i in range(size):
        tp[i] = (x[i] + x[i] + x[i]) / 3.0
    for i in range(n - 1, size):
        mean = _seq_mean(tp, i - n + 1, i + 1)
        var = 0.0
        for j in range(i - n + 1, i + 1):
            v = tp[j] - mean
            var += v * v
        std = math.sqrt(var / n)
        upper[i] = mean + k * std
        middle[i] = mean
        lower[i] = mean - k * std
    return upper, middle, lower


def bbands(x: F64, n: int, k: float) -> tuple[F64, F64, F64, F64]:
    upper, middle, lower = _bollinger(x, n, k)
    with np.errstate(invalid="ignore", divide="ignore"):
        width = (upper - lower) / middle
    return middle, upper, lower, width


@nb.njit(cache=True)
def true_range(high: F64, low: F64, close: F64) -> F64:
    out = np.empty(len(close))
    prev = close[0] if len(close) else 0.0
    for i in range(len(close)):
        out[i] = max(prev, high[i]) - min(low[i], prev)
        prev = close[i]
    return out


def atr(high: F64, low: F64, close: F64, n: int) -> F64:
    return wilder(true_range(high, low, close), n)


def keltner(high: F64, low: F64, close: F64, n: int, k: float) -> tuple[F64, F64, F64]:
    tp = (high + low + close) / 3.0
    mid = ema(tp, n)
    a = _ema_values(true_range(high, low, close), 1.0 / n)
    upper, lower = mid + a * k, mid - a * k
    return mid, upper, lower


@nb.njit(cache=True)
def _stoch(high: F64, low: F64, close: F64, k_period: int, d_period: int, smooth: int) -> tuple[F64, F64]:
    """Nautilus ``Stochastics(k, d, smooth, SIMPLE, 'moving_average')`` including its flat-window skip."""
    size = len(close)
    k_out, d_out = np.full(size, NAN), np.full(size, NAN)
    raw_hist = np.empty(size)  # inputs fed to the slowing SMA
    slow_hist = np.empty(size)  # inputs fed to the %D SMA
    n_raw = n_slow = 0
    value_k = value_d = 0.0
    initialized = False
    for i in range(size):
        lo_i = max(0, i - k_period + 1)
        hh, ll = high[lo_i], low[lo_i]
        for j in range(lo_i, i + 1):
            hh = max(hh, high[j])
            ll = min(ll, low[j])
        if hh != ll:
            raw_k = 100.0 * ((close[i] - ll) / (hh - ll))
            if smooth > 1:
                raw_hist[n_raw] = raw_k
                n_raw += 1
                value_k = _seq_mean(raw_hist, max(0, n_raw - smooth), n_raw)
            else:
                value_k = raw_k
            slow_hist[n_slow] = value_k
            n_slow += 1
            value_d = _seq_mean(slow_hist, max(0, n_slow - d_period), n_slow)
            if not initialized and i + 1 >= k_period and (smooth == 1 or n_raw >= smooth) and n_slow >= d_period:
                initialized = True
        if initialized:
            k_out[i], d_out[i] = value_k, value_d
    return k_out, d_out


def stoch(high: F64, low: F64, close: F64, k: int, d: int, smooth: int) -> tuple[F64, F64]:
    return _stoch(high, low, close, k, d, smooth)


@nb.njit(cache=True)
def _adx(high: F64, low: F64, close: F64, n: int) -> tuple[F64, F64, F64]:
    size = len(close)
    adx_out, pdi_out, mdi_out = np.full(size, NAN), np.full(size, NAN), np.full(size, NAN)
    alpha = 1.0 / n
    tr_s = p_s = m_s = adx_s = 0.0
    count = adx_count = 0
    plus_di = minus_di = 0.0
    for i in range(1, size):
        up, down = high[i] - high[i - 1], low[i - 1] - low[i]
        p_dm = up if (up > down and up > 0.0) else 0.0
        m_dm = down if (down > up and down > 0.0) else 0.0
        tr = max(high[i], close[i - 1]) - min(low[i], close[i - 1])
        if count == 0:
            tr_s, p_s, m_s = tr, p_dm, m_dm
        tr_s = alpha * tr + (1.0 - alpha) * tr_s
        p_s = alpha * p_dm + (1.0 - alpha) * p_s
        m_s = alpha * m_dm + (1.0 - alpha) * m_s
        count += 1
        if count < n:
            continue
        plus_di = 100.0 * p_s / tr_s if tr_s > 0.0 else 0.0
        minus_di = 100.0 * m_s / tr_s if tr_s > 0.0 else 0.0
        total = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / total if total > 0.0 else 0.0
        if adx_count == 0:
            adx_s = dx
        adx_s = alpha * dx + (1.0 - alpha) * adx_s
        adx_count += 1
        if adx_count >= n:
            adx_out[i], pdi_out[i], mdi_out[i] = adx_s, plus_di, minus_di
    return adx_out, pdi_out, mdi_out


def adx(high: F64, low: F64, close: F64, n: int) -> tuple[F64, F64, F64]:
    return _adx(high, low, close, n)


@nb.njit(cache=True)
def _rolling_extreme(x: F64, n: int, highest: bool) -> F64:
    out = np.full(len(x), NAN)
    for i in range(n - 1, len(x)):
        v = x[i - n + 1]
        for j in range(i - n + 2, i + 1):
            v = max(v, x[j]) if highest else min(v, x[j])
        out[i] = v
    return out


def highest(x: F64, n: int) -> F64:
    return _rolling_extreme(x, n, True)


def lowest(x: F64, n: int) -> F64:
    return _rolling_extreme(x, n, False)


def donchian(high: F64, low: F64, n: int) -> tuple[F64, F64, F64]:
    upper, lower = highest(high, n), lowest(low, n)
    return (upper + lower) / 2, upper, lower


@nb.njit(cache=True)
def _vwap(high: F64, low: F64, close: F64, volume: F64, day: npt.NDArray[np.int64]) -> F64:
    """Nautilus VWAP keyed by the bar-open day of month; zero-volume bars keep the previous value."""
    out = np.empty(len(close))
    current_day = -1
    pv = vol = value = 0.0
    for i in range(len(close)):
        price = (high[i] + low[i] + close[i]) / 3.0  # same order as the streaming runtime (BarValues.field)
        if day[i] != current_day:
            current_day = day[i]
            pv = vol = 0.0
            value = price
        if volume[i] != 0.0:
            pv += price * volume[i]
            vol += volume[i]
            value = pv / vol
        out[i] = value
    return out


def vwap(high: F64, low: F64, close: F64, volume: F64, day_of_month: npt.NDArray[np.int64]) -> F64:
    return _vwap(high, low, close, volume, day_of_month)


@nb.njit(cache=True)
def _roc(x: F64, n: int) -> F64:
    out = np.full(len(x), NAN)
    for i in range(n, len(x)):
        out[i] = ((x[i] - x[i - n]) / x[i - n]) * 100.0
    return out


def roc(x: F64, n: int) -> F64:
    return _roc(x, n)


@nb.njit(cache=True)
def _cci(high: F64, low: F64, close: F64, n: int) -> F64:
    size = len(close)
    out = np.full(size, NAN)
    tp = np.empty(size)
    for i in range(size):
        tp[i] = (high[i] + low[i] + close[i]) / 3.0
    for i in range(n - 1, size):
        mean = _seq_mean(tp, i - n + 1, i + 1)
        mad = 0.0
        for j in range(i - n + 1, i + 1):
            mad += abs(tp[j] - mean)
        mad /= n
        out[i] = (tp[i] - mean) / (0.015 * mad) if mad > 0.0 else 0.0
    return out


def cci(high: F64, low: F64, close: F64, n: int) -> F64:
    return _cci(high, low, close, n)


@nb.njit(cache=True)
def _obv(close: F64, volume: F64) -> F64:
    out = np.empty(len(close))
    value = 0.0
    for i in range(len(close)):
        if i > 0:
            if close[i] > close[i - 1]:
                value += volume[i]
            elif close[i] < close[i - 1]:
                value -= volume[i]
        out[i] = value
    return out


def obv(close: F64, volume: F64) -> F64:
    return _obv(close, volume)
