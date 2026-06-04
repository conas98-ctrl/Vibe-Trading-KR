"""Built-in Kiwoom OpenAPI+ Windows bridge profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

KIWOOM_OPENAPI_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="kiwoom-openapi-live-bridge-readonly",
        connector="kiwoom-openapi",
        label="Kiwoom OpenAPI+ · Windows Bridge Read-Only",
        environment="live",
        transport="local_bridge",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes=(
            "Uses a user-run Windows localhost bridge for Kiwoom OpenAPI+ COM/OCX. "
            "This profile stays read-only until a bridge trading profile is explicitly added."
        ),
    ),
)

