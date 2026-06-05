"""Built-in Daishin CYBOS/CREON Plus Windows bridge profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

DAISHIN_CYBOS_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="daishin-cybos-live-bridge-readonly",
        connector="daishin-cybos",
        label="Daishin CYBOS/CREON Plus · Windows Bridge Read-Only",
        environment="live",
        transport="local_bridge",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes=(
            "Uses a user-run Windows localhost bridge for Daishin CYBOS/CREON Plus COM. "
            "This profile stays read-only until a bridge trading profile is explicitly added."
        ),
    ),
)
