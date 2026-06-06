"""Built-in Yuanta tRadar Open API Windows bridge profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

YUANTA_TRADAR_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="yuanta-tradar-live-bridge-readonly",
        connector="yuanta-tradar",
        label="Yuanta tRadar Open API · Windows Bridge Read-Only",
        environment="live",
        transport="local_bridge",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes=(
            "Uses a user-run Windows localhost bridge for Yuanta tRadar Open API COM/DLL. "
            "This profile stays read-only until a bridge trading profile is explicitly added."
        ),
    ),
)
