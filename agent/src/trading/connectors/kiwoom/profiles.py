"""Built-in Kiwoom REST OpenAPI connector profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

KIWOOM_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="kiwoom-paper-sdk",
        connector="kiwoom",
        label="Kiwoom REST OpenAPI · Mock/Paper Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper"},
        notes="Reads Kiwoom REST OpenAPI mock/paper endpoints when credentials are configured.",
    ),
    TradingProfile(
        id="kiwoom-live-sdk-readonly",
        connector="kiwoom",
        label="Kiwoom REST OpenAPI · Live Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes="Reads Kiwoom REST OpenAPI live endpoints. Order placement is not exposed in this profile.",
    ),
    TradingProfile(
        id="kiwoom-paper-trade",
        connector="kiwoom",
        label="Kiwoom REST OpenAPI · Mock/Paper Trading",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place",),
        readonly=False,
        config={"profile": "paper"},
        notes="Places and cancels Kiwoom REST mock/paper orders only.",
    ),
    TradingProfile(
        id="kiwoom-live-trade",
        connector="kiwoom",
        label="Kiwoom REST OpenAPI · Live Trading",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place.requires_mandate",),
        readonly=False,
        config={"profile": "live"},
        notes="Live Kiwoom REST orders must pass Vibe-Trading mandate, kill switch, pre-trade, and audit gates.",
    ),
)
