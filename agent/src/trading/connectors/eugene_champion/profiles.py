"""Built-in Eugene Champion Open API Windows bridge profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

EUGENE_CHAMPION_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="eugene-champion-live-bridge-readonly",
        connector="eugene-champion",
        label="Eugene Champion Open API · Windows Bridge Read-Only",
        environment="live",
        transport="local_bridge",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes=(
            "Uses a user-run Windows localhost bridge for Eugene Champion Open API OCX/DLL. "
            "This profile stays read-only until a bridge trading profile is explicitly added."
        ),
    ),
)
