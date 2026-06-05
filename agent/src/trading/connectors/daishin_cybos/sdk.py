"""Daishin CYBOS/CREON Plus Windows bridge connector bootstrap."""

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

CONFIG_FILENAME = "daishin-cybos-bridge.json"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8766"
LABEL = "Daishin CYBOS/CREON bridge"
CONNECTOR = "daishin-cybos"


def config_path() -> Path:
    return get_runtime_root() / CONFIG_FILENAME


def load_config() -> KoreanConnectorConfig:
    return _load_config(config_path(), connector=CONNECTOR, bridge_url=DEFAULT_BRIDGE_URL)


def save_config(config: KoreanConnectorConfig) -> Path:
    return _save_config(config_path(), config)


def build_config(profile_config: Mapping[str, Any] | None = None, overrides: Mapping[str, Any] | None = None) -> KoreanConnectorConfig:
    return _build_config(
        config_path=config_path(),
        connector=CONNECTOR,
        profile_config=profile_config,
        overrides=overrides,
        bridge_url=DEFAULT_BRIDGE_URL,
    )


def check_status(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return _check_status(config or load_config(), label=LABEL, bridge=True)


def get_account_snapshot(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="account snapshot", bridge=True)


def get_positions(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="positions", bridge=True)


def get_open_orders(config: KoreanConnectorConfig | None = None, *, include_executions: bool = False) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="open orders", bridge=True)


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, **_: Any) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation=f"quote {symbol}", bridge=True)


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    **_: Any,
) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation=f"history {symbol}", bridge=True)
