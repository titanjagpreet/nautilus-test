"""The Numba trading loop: one pass over 1-minute bars, base-bar decisions at bar closes.

Line-by-line mirror of ``spec/decisions.py`` (decisions) and of what the NautilusTrader execution feed makes the
venue do (ARCHITECTURE.md "Execution semantics"). Per minute ``m``:

1. funding events due at or before the minute's open are charged (position after all fills so far, price =
   previous minute's close);
2. the open is checked against resting stop / take-profit (gap fills: stop at the open, target at its limit);
3. orders decided at the previous base close execute at the open: exit, then entry (stop/target placed from
   the fill; a new stop already through the open fills immediately), then a trailing-stop change (rejected,
   keeping the old stop, if the new level is already through the open — NautilusTrader rejects such modifies);
4. the adverse extreme (low for longs, high for shorts) then the favourable one are checked: **stop first**;
5. if a base bar closes after this minute, the strategy decides (fills happen at the next minute's open).
"""

from __future__ import annotations

import math

import numba as nb
import numpy as np
import numpy.typing as npt

F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
B1 = npt.NDArray[np.bool_]

# reason codes
RULE, STOP, TARGET, TIME, REVERSE, END = 0, 1, 2, 3, 4, 5
REASONS = ("rule", "stop", "target", "time", "reverse", "end")
# parameter codes
LONG_ONLY, SHORT_ONLY, BOTH = 0, 1, 2
PCT, ATR, STRUCTURE, RR, NONE = 0, 1, 2, 3, -1
SIZING_PCT, SIZING_FIXED = 0, 1


@nb.njit(cache=True)
def _round(value: float, scale: float) -> float:
    """Half away from zero to the price/fee grid (``spec.decisions.round_price``)."""
    return math.copysign(math.floor(abs(value) * scale + 0.5), value) / scale


@nb.njit(cache=True)
def simulate(
    m_open: F64,
    m_high: F64,
    m_low: F64,
    m_close: F64,
    m_base_close: I64,
    b_close: F64,
    b_day: I64,
    entry_long: B1,
    exit_long: B1,
    entry_short: B1,
    exit_short: B1,
    risk_ready: B1,
    atr_stop: F64,
    atr_target: F64,
    atr_trail: F64,
    lowest_low: F64,
    highest_high: F64,
    f_minute: I64,
    f_rate: F64,
    params: F64,
) -> tuple[F64, F64]:
    """Return (trades[n, 11], funding[n, 4]).

    trades columns: side(+1/-1), qty, entry_minute, entry_price, exit_minute, exit_price, reason, entry_fee,
    exit_fee, funding, unused. funding columns: event index, position size, price, amount.
    ``params`` layout: see ``engines.fast.runner.pack_params``.
    """
    direction = int(params[0])
    sizing_kind, sizing_value, leverage = int(params[1]), params[2], params[3]
    stop_kind, stop_value = int(params[4]), params[5]
    tp_kind, tp_value = int(params[6]), params[7]
    trail_kind, trail_value = int(params[8]), params[9]
    time_exit, cooldown, max_per_day = int(params[10]), int(params[11]), int(params[12])
    slip, taker, maker = params[13], params[14], params[15]
    price_scale, size_scale, min_qty, balance = params[16], params[17], params[18], params[19]
    fee_scale = 1e8  # USDC precision in NautilusTrader

    n_min, n_base, n_fund = len(m_open), len(b_close), len(f_rate)
    trades = np.zeros((n_base + 2, 11))
    funding_out = np.zeros((n_fund, 4))
    n_trades = 0
    n_pay = 0

    side = 0  # +1 long, -1 short, 0 flat
    qty = entry_price = stop = target = 0.0
    entry_minute = 0
    entry_fee = trade_funding = 0.0
    bars_held = 0
    bars_since_exit = -1
    day_counted = -1
    entries_today = 0

    pend_exit = False
    pend_exit_reason = RULE
    pend_entry = 0
    pend_qty = 0.0
    pend_atr_stop = pend_atr_target = pend_low = pend_high = 0.0
    pend_trail = math.nan

    next_fund = 0
    last_close = m_open[0]

    for m in range(n_min + 1):
        final = m == n_min
        # 1. funding due before this minute (at the end: due at or before the last base close)
        while next_fund < n_fund and (f_minute[next_fund] <= m if not final else f_minute[next_fund] <= n_min):
            if side != 0:
                size = side * qty
                amount = size * last_close * f_rate[next_fund]  # ledger: raw amount; balance: USDC-rounded
                balance -= _round(amount, fee_scale)
                trade_funding += amount
                funding_out[n_pay, 0] = next_fund
                funding_out[n_pay, 1] = size
                funding_out[n_pay, 2] = last_close
                funding_out[n_pay, 3] = amount
                n_pay += 1
            next_fund += 1
        if final:
            break

        o, h, lo, c = m_open[m], m_high[m], m_low[m], m_close[m]
        exit_px = math.nan
        exit_reason = RULE
        # 2. gap check of resting orders at the open
        if side == 1:
            if o <= stop:
                exit_px, exit_reason = _round(o - slip, price_scale), STOP
            elif target > 0.0 and o >= target:
                exit_px, exit_reason = target, TARGET
        elif side == -1:
            if o >= stop:
                exit_px, exit_reason = _round(o + slip, price_scale), STOP
            elif target > 0.0 and o <= target:
                exit_px, exit_reason = target, TARGET
        # 3a. pending market exit
        if side != 0 and math.isnan(exit_px) and pend_exit:
            exit_px, exit_reason = _round(o - side * slip, price_scale), pend_exit_reason
        if side != 0 and not math.isnan(exit_px):
            fee = _round(qty * exit_px * (maker if exit_reason == TARGET else taker), fee_scale)
            gross = side * qty * (exit_px - entry_price)
            balance += gross - fee
            trades[n_trades, 0] = side
            trades[n_trades, 1] = qty
            trades[n_trades, 2] = entry_minute
            trades[n_trades, 3] = entry_price
            trades[n_trades, 4] = m
            trades[n_trades, 5] = exit_px
            trades[n_trades, 6] = exit_reason
            trades[n_trades, 7] = entry_fee
            trades[n_trades, 8] = fee
            trades[n_trades, 9] = trade_funding
            n_trades += 1
            side = 0
            bars_since_exit = 0
        pend_exit = False
        # 3b. pending entry
        if pend_entry != 0:
            side = pend_entry
            qty = pend_qty
            entry_price = _round(o + side * slip, price_scale)
            entry_minute = m
            entry_fee = _round(qty * entry_price * taker, fee_scale)
            balance -= entry_fee
            trade_funding = 0.0
            bars_held = 0
            if stop_kind == PCT:
                raw_stop = entry_price * (1.0 - side * stop_value / 100.0)
            elif stop_kind == ATR:
                raw_stop = entry_price - side * stop_value * pend_atr_stop
            else:
                level = pend_low if side == 1 else pend_high
                raw_stop = level * (1.0 - side * stop_value / 100.0)
            stop = _round(raw_stop, price_scale)
            if tp_kind == PCT:
                target = _round(entry_price * (1.0 + side * tp_value / 100.0), price_scale)
            elif tp_kind == ATR:
                target = _round(entry_price + side * tp_value * pend_atr_target, price_scale)
            elif tp_kind == RR:
                target = _round(entry_price + side * tp_value * abs(entry_price - stop), price_scale)
            else:
                target = 0.0
            pend_entry = 0
            # a new stop already through the market fills at once (venue reject_stop_orders=False)
            if (side == 1 and o <= stop) or (side == -1 and o >= stop):
                exit_px = _round(o - side * slip, price_scale)
                fee = _round(qty * exit_px * taker, fee_scale)
                balance += side * qty * (exit_px - entry_price) - fee
                trades[n_trades, 0] = side
                trades[n_trades, 1] = qty
                trades[n_trades, 2] = entry_minute
                trades[n_trades, 3] = entry_price
                trades[n_trades, 4] = m
                trades[n_trades, 5] = exit_px
                trades[n_trades, 6] = STOP
                trades[n_trades, 7] = entry_fee
                trades[n_trades, 8] = fee
                trades[n_trades, 9] = trade_funding
                n_trades += 1
                side = 0
                bars_since_exit = 0
        # 3c. trailing-stop change: a modification that is already through the market is rejected by the venue
        if not math.isnan(pend_trail):
            if side != 0 and not ((side == 1 and o <= pend_trail) or (side == -1 and o >= pend_trail)):
                stop = pend_trail
            pend_trail = math.nan
        # 4. intrabar: adverse extreme first, then the favourable one
        if side != 0:
            exit_px = math.nan
            if side == 1:
                if lo <= stop:
                    exit_px, exit_reason = _round(stop - slip, price_scale), STOP
                elif target > 0.0 and h >= target:
                    exit_px, exit_reason = target, TARGET
            elif h >= stop:
                exit_px, exit_reason = _round(stop + slip, price_scale), STOP
            elif target > 0.0 and lo <= target:
                exit_px, exit_reason = target, TARGET
            if not math.isnan(exit_px):
                fee = _round(qty * exit_px * (maker if exit_reason == TARGET else taker), fee_scale)
                balance += side * qty * (exit_px - entry_price) - fee
                trades[n_trades, 0] = side
                trades[n_trades, 1] = qty
                trades[n_trades, 2] = entry_minute
                trades[n_trades, 3] = entry_price
                trades[n_trades, 4] = m
                trades[n_trades, 5] = exit_px
                trades[n_trades, 6] = exit_reason
                trades[n_trades, 7] = entry_fee
                trades[n_trades, 8] = fee
                trades[n_trades, 9] = trade_funding
                n_trades += 1
                side = 0
                bars_since_exit = 0
        last_close = c

        # 5. base-bar close → decide
        b = m_base_close[m]
        if b < 0:
            continue
        if side != 0:
            bars_held += 1
        if bars_since_exit >= 0:
            bars_since_exit += 1
        if b == n_base - 1:
            # end of data: apply remaining funding due by the last close, then close at the last close
            while next_fund < n_fund and f_minute[next_fund] <= n_min:
                if side != 0:
                    size = side * qty
                    amount = size * last_close * f_rate[next_fund]
                    balance -= _round(amount, fee_scale)
                    trade_funding += amount
                    funding_out[n_pay, 0] = next_fund
                    funding_out[n_pay, 1] = size
                    funding_out[n_pay, 2] = last_close
                    funding_out[n_pay, 3] = amount
                    n_pay += 1
                next_fund += 1
            if side != 0:
                exit_px = _round(c - side * slip, price_scale)
                fee = _round(qty * exit_px * taker, fee_scale)
                balance += side * qty * (exit_px - entry_price) - fee
                trades[n_trades, 0] = side
                trades[n_trades, 1] = qty
                trades[n_trades, 2] = entry_minute
                trades[n_trades, 3] = entry_price
                trades[n_trades, 4] = n_min  # after the last minute (reported as the last base close)
                trades[n_trades, 5] = exit_px
                trades[n_trades, 6] = END
                trades[n_trades, 7] = entry_fee
                trades[n_trades, 8] = fee
                trades[n_trades, 9] = trade_funding
                n_trades += 1
                side = 0
            break
        if not risk_ready[b]:
            continue

        # decisions (spec.decisions.decide)
        can_long = direction != SHORT_ONLY and entry_long[b]
        can_short = direction != LONG_ONLY and entry_short[b]
        if can_long and can_short:
            can_long = can_short = False
        if b_day[b] != day_counted:
            day_counted, entries_today = b_day[b], 0
        cooldown_ok = bars_since_exit < 0 or bars_since_exit >= cooldown
        day_ok = max_per_day < 0 or entries_today < max_per_day
        do_exit = False
        enter = 0
        if side != 0:
            if time_exit >= 0 and bars_held >= time_exit:
                do_exit, pend_exit_reason = True, TIME
            elif (side == 1 and exit_long[b]) or (side == -1 and exit_short[b]):
                do_exit, pend_exit_reason = True, RULE
            opposite = can_short if side == 1 else can_long
            if opposite and day_ok and cooldown == 0:
                if not do_exit:
                    do_exit, pend_exit_reason = True, REVERSE
                enter = -side
        elif cooldown_ok and day_ok:
            if can_long:
                enter = 1
            elif can_short:
                enter = -1
        if do_exit:
            pend_exit = True
        if enter != 0:
            ref = b_close[b]
            notional = balance * sizing_value / 100.0 if sizing_kind == SIZING_PCT else sizing_value
            notional = min(notional, max(balance, 0.0) * leverage)
            q = math.floor(notional / ref * size_scale + 1e-9) / size_scale
            if q >= min_qty:
                pend_entry = enter
                pend_qty = q
                pend_atr_stop, pend_atr_target = atr_stop[b], atr_target[b]
                pend_low, pend_high = lowest_low[b], highest_high[b]
                entries_today += 1
                continue
        if not do_exit and side != 0 and trail_kind != NONE:
            if trail_kind == PCT:
                cand = _round(b_close[b] * (1.0 - side * trail_value / 100.0), price_scale)
            else:
                cand = _round(b_close[b] - side * trail_value * atr_trail[b], price_scale)
            if (side == 1 and cand > stop) or (side == -1 and cand < stop):
                pend_trail = cand

    return trades[:n_trades], funding_out[:n_pay]
