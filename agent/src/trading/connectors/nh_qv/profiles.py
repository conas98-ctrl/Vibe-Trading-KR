"""Built-in NH QV Open API Windows bridge profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

NH_QV_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="nh-qv-live-bridge-readonly",
        connector="nh-qv",
        label="NH QV Open API · Windows Bridge Read-Only",
        environment="live",
        transport="local_bridge",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes=(
            "Uses a user-run Windows localhost bridge for NH QV Open API 32-bit DLL. "
            "This profile stays read-only until a bridge trading profile is explicitly added."
        ),
    ),
)
