"""Korean-market connector registration and safety contracts."""

from __future__ import annotations

from typing import get_args

import pytest

from src.live.classification import ToolClass
from src.live.mandate.model import AssetClass, InstrumentType
from src.trading import profiles, service
from src.trading.types import Transport

pytestmark = pytest.mark.unit


def test_kr_asset_classes_and_local_bridge_transport_are_supported() -> None:
    assert AssetClass.KR_EQUITY.value == "kr_equity"
    assert AssetClass.KR_ETF.value == "kr_etf"
    assert AssetClass.KR_DERIVATIVE.value == "kr_derivative"
    assert AssetClass.KR_BOND.value == "kr_bond"
    assert AssetClass.KR_ELW.value == "kr_elw"
    assert InstrumentType.FUTURE.value == "future"
    assert "local_bridge" in get_args(Transport)


def test_korean_broker_profiles_registered() -> None:
    ids = {p.id for p in profiles.list_profiles()}
    assert {
        "kis-paper-sdk",
        "kis-live-sdk-readonly",
        "kis-paper-trade",
        "kis-live-trade",
        "ls-paper-sdk",
        "ls-live-sdk-readonly",
        "ls-paper-trade",
        "ls-live-trade",
        "db-paper-sdk",
        "db-live-sdk-readonly",
        "db-paper-trade",
        "db-live-trade",
        "kiwoom-paper-sdk",
        "kiwoom-live-sdk-readonly",
        "kiwoom-paper-trade",
        "kiwoom-live-trade",
        "kiwoom-openapi-live-bridge-readonly",
        "daishin-cybos-live-bridge-readonly",
        "eugene-champion-live-bridge-readonly",
        "yuanta-tradar-live-bridge-readonly",
        "nh-qv-live-bridge-readonly",
    } <= ids


@pytest.mark.parametrize(
    "profile_id, connector, transport, readonly",
    [
        ("kis-paper-sdk", "kis", "broker_sdk", True),
        ("kis-live-trade", "kis", "broker_sdk", False),
        ("ls-paper-sdk", "ls", "broker_sdk", True),
        ("db-live-trade", "db", "broker_sdk", False),
        ("kiwoom-live-trade", "kiwoom", "broker_sdk", False),
        ("kiwoom-openapi-live-bridge-readonly", "kiwoom-openapi", "local_bridge", True),
        ("daishin-cybos-live-bridge-readonly", "daishin-cybos", "local_bridge", True),
        ("eugene-champion-live-bridge-readonly", "eugene-champion", "local_bridge", True),
        ("yuanta-tradar-live-bridge-readonly", "yuanta-tradar", "local_bridge", True),
        ("nh-qv-live-bridge-readonly", "nh-qv", "local_bridge", True),
    ],
)
def test_korean_profiles_carry_connector_transport_and_trade_gate(profile_id, connector, transport, readonly) -> None:
    profile = profiles.profile_by_id(profile_id)
    assert profile.connector == connector
    assert profile.transport == transport
    assert profile.readonly is readonly
    if profile.environment == "live" and not readonly:
        assert "orders.place.requires_mandate" in profile.capabilities


@pytest.mark.parametrize(
    "connector, profile_id",
    [
        ("kis", "kis-paper-sdk"),
        ("ls", "ls-paper-sdk"),
        ("db", "db-paper-sdk"),
        ("kiwoom", "kiwoom-paper-sdk"),
        ("kiwoom-openapi", "kiwoom-openapi-live-bridge-readonly"),
        ("daishin-cybos", "daishin-cybos-live-bridge-readonly"),
        ("eugene-champion", "eugene-champion-live-bridge-readonly"),
        ("yuanta-tradar", "yuanta-tradar-live-bridge-readonly"),
        ("nh-qv", "nh-qv-live-bridge-readonly"),
    ],
)
def test_korean_connectors_degrade_cleanly_when_unconfigured(connector, profile_id, monkeypatch, tmp_path) -> None:
    module = service._sdk_module(connector)
    monkeypatch.setattr(module, "get_runtime_root", lambda: tmp_path, raising=False)
    result = service.check_connection(profile_id)
    assert result["status"] == "error"
    assert result["connector"] == connector
    assert "not configured" in result["error"].lower()


@pytest.mark.parametrize("symbol", ["005930", "005930.KS", "KRX:005930", "KR.005930"])
def test_korean_equity_symbols_route_to_kr_equity_mandate_bucket(symbol) -> None:
    instrument, asset_class = service._order_classification("kis", symbol)
    assert instrument is InstrumentType.EQUITY
    assert asset_class is AssetClass.KR_EQUITY


def test_korean_connector_read_write_classification_maps() -> None:
    from src.trading.connectors.kis.classification import KIS_TOOL_CLASS
    from src.trading.connectors.kiwoom.classification import KIWOOM_TOOL_CLASS
    from src.trading.connectors.ls.classification import LS_TOOL_CLASS
    from src.trading.connectors.db.classification import DB_TOOL_CLASS

    assert KIS_TOOL_CLASS["inquire_price"] is ToolClass.READ
    assert KIS_TOOL_CLASS["ccnl_notice"] is ToolClass.READ
    assert KIS_TOOL_CLASS["program_trade_total"] is ToolClass.READ
    assert KIS_TOOL_CLASS["order_cash"] is ToolClass.WRITE
    assert LS_TOOL_CLASS["stock_quote"] is ToolClass.READ
    assert LS_TOOL_CLASS["stock_order"] is ToolClass.WRITE
    assert DB_TOOL_CLASS["stock_quote"] is ToolClass.READ
    assert DB_TOOL_CLASS["stock_order"] is ToolClass.WRITE
    assert KIWOOM_TOOL_CLASS["ka10001"] is ToolClass.READ
    assert KIWOOM_TOOL_CLASS["kt10000"] is ToolClass.WRITE


def test_kiwoom_websocket_smoke_service_routes_profile_and_safety_flags(monkeypatch, tmp_path) -> None:
    from src.trading.connectors.kiwoom import sdk as kiwoom

    calls: list[dict] = []

    async def fake_smoke_runner(config, **kwargs):
        calls.append({"config": config, "kwargs": kwargs})
        return {
            "status": "not_run",
            "connector": "kiwoom",
            "profile": config.profile,
            "environment": config.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "reason": "mocked smoke runner",
        }

    monkeypatch.setattr(kiwoom, "run_websocket_smoke_with_evidence", fake_smoke_runner)

    target = tmp_path / "kiwoom-websocket-smoke.json"
    result = service.run_websocket_smoke_with_evidence(
        "kiwoom-paper-sdk",
        channel="domestic_stock_realtime",
        symbols=["KRX:039490"],
        evidence_path=target,
        allow_broker_calls=False,
        allow_live=False,
        max_messages=2,
        max_samples=1,
    )

    assert result["status"] == "not_run"
    assert result["profile_id"] == "kiwoom-paper-sdk"
    assert result["connector"] == "kiwoom"
    assert result["environment"] == "paper"
    assert result["transport"] == "broker_sdk"
    assert calls[0]["config"].connector == "kiwoom"
    assert calls[0]["config"].profile == "paper"
    assert calls[0]["kwargs"] == {
        "channel": "domestic_stock_realtime",
        "symbols": ["KRX:039490"],
        "evidence_path": target,
        "max_messages": 2,
        "message_timeout": None,
        "connect_attempts": 1,
        "connect_backoff_seconds": 0.0,
        "reconnect_attempts": 0,
        "reconnect_backoff_seconds": 0.0,
        "max_samples": 1,
        "allow_broker_calls": False,
        "allow_live": False,
    }


def test_websocket_smoke_service_rejects_non_kiwoom_connectors(tmp_path) -> None:
    result = service.run_websocket_smoke_with_evidence(
        "kis-paper-sdk",
        symbols=["KRX:005930"],
        evidence_path=tmp_path / "kis-websocket-smoke.json",
    )

    assert result["status"] == "error"
    assert result["profile_id"] == "kis-paper-sdk"
    assert result["connector"] == "kis"
    assert result["transport"] == "broker_sdk"
    assert "websocket_smoke.run" in result["error"]
