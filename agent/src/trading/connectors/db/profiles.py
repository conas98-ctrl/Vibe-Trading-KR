"""Built-in DB Securities Open API connector profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

DB_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="db-paper-sdk",
        connector="db",
        label="DB Open API · Mock/Paper Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper"},
        notes="Reads DB Securities Open API mock/paper endpoints when credentials are configured.",
    ),
    TradingProfile(
        id="db-live-sdk-readonly",
        connector="db",
        label="DB Open API · Live Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes="Reads DB Securities live Open API. Order placement is not exposed in this profile.",
    ),
    TradingProfile(
        id="db-paper-trade",
        connector="db",
        label="DB Open API · Mock/Paper Trading",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place",),
        readonly=False,
        config={"profile": "paper"},
        notes="Places, revises, and cancels DB Securities mock/paper stock orders only.",
    ),
    TradingProfile(
        id="db-live-trade",
        connector="db",
        label="DB Open API · Live Trading",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place.requires_mandate",),
        readonly=False,
        config={"profile": "live"},
        notes="Live DB Securities orders must pass Vibe-Trading mandate, kill switch, pre-trade, and audit gates.",
    ),
)
