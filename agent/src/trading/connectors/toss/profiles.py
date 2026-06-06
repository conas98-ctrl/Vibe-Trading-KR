"""Built-in Toss Securities Open API connector profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

TOSS_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="toss-paper-sdk",
        connector="toss",
        label="Toss Securities Open API · Paper/Pre-Apply Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper"},
        notes="Reads Toss Securities Open API when OAuth client credentials and account sequence are configured.",
    ),
    TradingProfile(
        id="toss-live-sdk-readonly",
        connector="toss",
        label="Toss Securities Open API · Live Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes="Reads Toss Securities live Open API. Order placement is not exposed in this profile.",
    ),
    TradingProfile(
        id="toss-paper-trade",
        connector="toss",
        label="Toss Securities Open API · Paper/Pre-Apply Trading",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place",),
        readonly=False,
        config={"profile": "paper"},
        notes="Places and cancels Toss Securities orders only after OAuth credentials and account sequence are configured.",
    ),
    TradingProfile(
        id="toss-live-trade",
        connector="toss",
        label="Toss Securities Open API · Live Trading",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place.requires_mandate",),
        readonly=False,
        config={"profile": "live"},
        notes="Live Toss Securities orders must pass Vibe-Trading mandate, kill switch, pre-trade, and audit gates.",
    ),
)
