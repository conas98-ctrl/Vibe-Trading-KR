"""Built-in LS Securities connector profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

LS_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="ls-paper-sdk",
        connector="ls",
        label="LS OpenAPI · Mock/Paper Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper"},
        notes="Reads LS Securities OpenAPI mock/paper endpoints when credentials are configured.",
    ),
    TradingProfile(
        id="ls-live-sdk-readonly",
        connector="ls",
        label="LS OpenAPI · Live Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes="Reads LS Securities live OpenAPI. Order placement is not exposed in this profile.",
    ),
    TradingProfile(
        id="ls-paper-trade",
        connector="ls",
        label="LS OpenAPI · Mock/Paper Trading",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place",),
        readonly=False,
        config={"profile": "paper"},
        notes="Places and cancels LS mock/paper orders only.",
    ),
    TradingProfile(
        id="ls-live-trade",
        connector="ls",
        label="LS OpenAPI · Live Trading",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place.requires_mandate",),
        readonly=False,
        config={"profile": "live"},
        notes="Live LS orders must pass Vibe-Trading mandate, kill switch, pre-trade, and audit gates.",
    ),
)
