"""Built-in Korean Investment & Securities connector profiles."""

from __future__ import annotations

from src.trading.types import READ_CAPABILITIES, TradingProfile

KIS_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="kis-paper-sdk",
        connector="kis",
        label="KIS Open API · Mock/Paper Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper"},
        notes="Reads KIS mock investment Open API when app credentials are configured.",
    ),
    TradingProfile(
        id="kis-live-sdk-readonly",
        connector="kis",
        label="KIS Open API · Live Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly"},
        notes="Reads KIS live Open API. Order placement is not exposed in this profile.",
    ),
    TradingProfile(
        id="kis-paper-trade",
        connector="kis",
        label="KIS Open API · Mock/Paper Trading",
        environment="paper",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place",),
        readonly=False,
        config={"profile": "paper"},
        notes="Places and cancels orders through KIS mock investment endpoints only.",
    ),
    TradingProfile(
        id="kis-live-trade",
        connector="kis",
        label="KIS Open API · Live Trading",
        environment="live",
        transport="broker_sdk",
        capabilities=READ_CAPABILITIES + ("orders.place.requires_mandate",),
        readonly=False,
        config={"profile": "live"},
        notes="Live KIS orders must pass Vibe-Trading mandate, kill switch, pre-trade, and audit gates.",
    ),
)
