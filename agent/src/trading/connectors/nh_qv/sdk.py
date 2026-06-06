"""NH QV Open API Windows bridge connector bootstrap."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.config.paths import get_runtime_root
from src.trading.connectors.kr_bridge import (
    check_bridge_status,
    get_account_snapshot as _bridge_account_snapshot,
    get_historical_bars as _bridge_historical_bars,
    get_open_orders as _bridge_open_orders,
    get_positions as _bridge_positions,
    get_quote as _bridge_quote,
)
from src.trading.connectors.kr_common import (
    KoreanConnectorConfig,
    build_config as _build_config,
    load_config as _load_config,
    save_config as _save_config,
)

CONFIG_FILENAME = "nh-qv-bridge.json"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8769"
LABEL = "NH QV Open API bridge"
CONNECTOR = "nh-qv"


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


def check_status(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    return check_bridge_status(config or load_config(), label=LABEL, client=client)


def get_account_snapshot(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    return _bridge_account_snapshot(config or load_config(), label=LABEL, client=client)


def get_positions(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    return _bridge_positions(config or load_config(), label=LABEL, client=client)


def get_open_orders(
    config: KoreanConnectorConfig | None = None,
    *,
    include_executions: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    return _bridge_open_orders(config or load_config(), label=LABEL, include_executions=include_executions, client=client)


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, client: Any | None = None, **_: Any) -> dict[str, Any]:
    return _bridge_quote(symbol, config=config or load_config(), label=LABEL, client=client)


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    client: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    return _bridge_historical_bars(
        symbol,
        config=config or load_config(),
        label=LABEL,
        period=period,
        limit=limit,
        client=client,
    )
