"""Kiwoom REST OpenAPI connector bootstrap."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.config.paths import get_runtime_root
from src.trading.connectors.kr_common import (
    KoreanConnectorConfig,
    build_config as _build_config,
    check_status as _check_status,
    load_config as _load_config,
    save_config as _save_config,
    unsupported_or_unconfigured,
)

CONFIG_FILENAME = "kiwoom.json"
PAPER_URL = "https://mockapi.kiwoom.com"
LIVE_URL = "https://api.kiwoom.com"
LABEL = "Kiwoom REST OpenAPI"
CONNECTOR = "kiwoom"


def config_path() -> Path:
    return get_runtime_root() / CONFIG_FILENAME


def load_config() -> KoreanConnectorConfig:
    return _load_config(config_path(), connector=CONNECTOR, paper_url=PAPER_URL, live_url=LIVE_URL)


def save_config(config: KoreanConnectorConfig) -> Path:
    return _save_config(config_path(), config)


def build_config(profile_config: Mapping[str, Any] | None = None, overrides: Mapping[str, Any] | None = None) -> KoreanConnectorConfig:
    return _build_config(
        config_path=config_path(),
        connector=CONNECTOR,
        profile_config=profile_config,
        overrides=overrides,
        paper_url=PAPER_URL,
        live_url=LIVE_URL,
    )


def check_status(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return _check_status(config or load_config(), label=LABEL)


def get_account_snapshot(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="account snapshot")


def get_positions(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="positions")


def get_open_orders(config: KoreanConnectorConfig | None = None, *, include_executions: bool = False) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="open orders")


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, **_: Any) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation=f"quote {symbol}")


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    **_: Any,
) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation=f"history {symbol}")


def place_order(config: KoreanConnectorConfig | None = None, **_: Any) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="place order")


def cancel_order(config: KoreanConnectorConfig | None = None, order_id: str = "", **_: Any) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation=f"cancel order {order_id}")
