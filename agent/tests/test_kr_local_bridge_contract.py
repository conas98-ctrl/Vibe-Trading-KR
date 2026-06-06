"""Read-only contract for Windows-only Korean broker local bridges."""

from __future__ import annotations

import importlib
from urllib.parse import parse_qs, urlparse

import pytest

from src.trading.connectors.daishin_cybos import sdk as daishin
from src.trading.connectors.kiwoom_openapi import sdk as kiwoom_openapi
from src.trading.connectors.kr_common import KoreanConnectorConfig

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _BridgeClient:
    def __init__(self, *, connector: str):
        self.connector = connector
        self.calls: list[dict] = []

    def get(self, url, *, headers=None, params=None, timeout=None):
        parsed = urlparse(url)
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        if params:
            query.update({k: str(v) for k, v in params.items()})
        self.calls.append({"method": "GET", "path": parsed.path, "query": query, "headers": headers or {}})
        if parsed.path == "/health":
            return _Response({"status": "ok", "connector": self.connector, "bridge_version": "0.1.0"})
        if parsed.path == "/account":
            return _Response({"status": "ok", "account": {"cash": 1000000, "currency": "KRW"}})
        if parsed.path == "/positions":
            return _Response({"status": "ok", "positions": [{"symbol": "005930", "quantity": 2}]})
        if parsed.path == "/orders":
            return _Response({"status": "ok", "open_orders": [{"order_id": "OID-1"}], "executions": []})
        if parsed.path == "/quote/005930":
            return _Response({"status": "ok", "symbol": "005930", "quote": {"last": 70000}})
        if parsed.path == "/history/005930":
            return _Response({"status": "ok", "symbol": "005930", "bars": [{"date": "20260604", "close": 70000}]})
        raise AssertionError(f"unexpected bridge path {parsed.path}")


def _load_bridge_module(module_or_path):
    if isinstance(module_or_path, str):
        return importlib.import_module(module_or_path)
    return module_or_path


@pytest.mark.parametrize(
    "module_or_path, connector, default_url",
    [
        (kiwoom_openapi, "kiwoom-openapi", kiwoom_openapi.DEFAULT_BRIDGE_URL),
        (daishin, "daishin-cybos", daishin.DEFAULT_BRIDGE_URL),
        ("src.trading.connectors.eugene_champion.sdk", "eugene-champion", "http://127.0.0.1:8767"),
        ("src.trading.connectors.yuanta_tradar.sdk", "yuanta-tradar", "http://127.0.0.1:8768"),
        ("src.trading.connectors.nh_qv.sdk", "nh-qv", "http://127.0.0.1:8769"),
    ],
)
def test_local_bridge_health_uses_bearer_token(module_or_path, connector, default_url) -> None:
    module = _load_bridge_module(module_or_path)
    cfg = KoreanConnectorConfig(connector=connector, profile="live-readonly", bridge_url=default_url, bridge_token="tok")
    client = _BridgeClient(connector=connector)
    out = module.check_status(cfg, client=client)
    assert out["status"] == "ok"
    assert out["connector"] == connector
    assert out["bridge"]["bridge_version"] == "0.1.0"
    assert client.calls[0]["path"] == "/health"
    assert client.calls[0]["headers"]["Authorization"] == "Bearer tok"


@pytest.mark.parametrize(
    "module_or_path, connector, default_url",
    [
        (kiwoom_openapi, "kiwoom-openapi", kiwoom_openapi.DEFAULT_BRIDGE_URL),
        (daishin, "daishin-cybos", daishin.DEFAULT_BRIDGE_URL),
        ("src.trading.connectors.eugene_champion.sdk", "eugene-champion", "http://127.0.0.1:8767"),
        ("src.trading.connectors.yuanta_tradar.sdk", "yuanta-tradar", "http://127.0.0.1:8768"),
        ("src.trading.connectors.nh_qv.sdk", "nh-qv", "http://127.0.0.1:8769"),
    ],
)
def test_local_bridge_read_operations_route_to_stable_paths(module_or_path, connector, default_url) -> None:
    module = _load_bridge_module(module_or_path)
    cfg = KoreanConnectorConfig(connector=connector, profile="live-readonly", bridge_url=default_url, bridge_token="tok")
    client = _BridgeClient(connector=connector)

    assert module.get_account_snapshot(cfg, client=client)["account"]["cash"] == 1000000
    assert module.get_positions(cfg, client=client)["positions"][0]["symbol"] == "005930"
    assert module.get_open_orders(cfg, include_executions=True, client=client)["open_orders"][0]["order_id"] == "OID-1"
    assert module.get_quote("005930.KS", config=cfg, client=client)["quote"]["last"] == 70000
    assert module.get_historical_bars("KRX:005930", config=cfg, period="1d", limit=5, client=client)["bars"][0]["close"] == 70000

    assert [call["path"] for call in client.calls] == [
        "/account",
        "/positions",
        "/orders",
        "/quote/005930",
        "/history/005930",
    ]
    assert client.calls[2]["query"]["include_executions"] == "true"
    assert client.calls[4]["query"] == {"period": "1d", "limit": "5"}


@pytest.mark.parametrize(
    "module_or_path",
    [
        kiwoom_openapi,
        daishin,
        "src.trading.connectors.eugene_champion.sdk",
        "src.trading.connectors.yuanta_tradar.sdk",
        "src.trading.connectors.nh_qv.sdk",
    ],
)
def test_local_bridge_fails_closed_without_token(module_or_path) -> None:
    module = _load_bridge_module(module_or_path)
    cfg = KoreanConnectorConfig(connector="x", profile="live-readonly", bridge_url="http://127.0.0.1:9999")
    out = module.check_status(cfg)
    assert out["status"] == "error"
    assert "bridge_token" in out["error"]


@pytest.mark.parametrize(
    "module_or_path",
    [
        kiwoom_openapi,
        daishin,
        "src.trading.connectors.eugene_champion.sdk",
        "src.trading.connectors.yuanta_tradar.sdk",
        "src.trading.connectors.nh_qv.sdk",
    ],
)
def test_local_bridge_modules_remain_read_only(module_or_path) -> None:
    module = _load_bridge_module(module_or_path)
    assert not hasattr(module, "place_order")
