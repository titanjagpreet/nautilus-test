"""Trading-cost settings shared by both engines: fee profiles and slippage.

Fee profiles live in ``config/fee_profiles.json`` so they can be edited without touching code; add a profile
there and it becomes selectable in specs, the API and the UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache

from strategy_lab.config import PROJECT_ROOT

FEE_PROFILES_PATH = PROJECT_ROOT / "config" / "fee_profiles.json"
MAX_SLIPPAGE_TICKS = 1  # NautilusTrader's FillModel can move a fill by at most one tick (LEARNINGS.md §4)


@dataclass(frozen=True)
class FeeProfile:
    name: str
    maker_bps: float
    taker_bps: float
    note: str = ""

    @property
    def maker_rate(self) -> float:
        return self.maker_bps / 10_000.0

    @property
    def taker_rate(self) -> float:
        return self.taker_bps / 10_000.0


@cache
def fee_profiles() -> dict[str, FeeProfile]:
    raw = json.loads(FEE_PROFILES_PATH.read_text())
    return {name: FeeProfile(name=name, **values) for name, values in raw.items()}


def fee_profile(name: str) -> FeeProfile:
    profiles = fee_profiles()
    if name not in profiles:
        raise KeyError(f"unknown fee profile {name!r}; known: {sorted(profiles)}")
    return profiles[name]
