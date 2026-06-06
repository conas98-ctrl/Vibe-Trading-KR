"""Credential-gated Korean broker smoke verification contracts."""

from __future__ import annotations

import pytest

from src.trading import kr_smoke
from src.tools import build_registry
from src.tools.trading_connector_tool import TradingKoreanSmokeTool

pytestmark = pytest.mark.unit


def test_korean_smoke_plan_is_readonly_and_explicitly_gated() -> None:
    plan = kr_smoke.build_smoke_plan()
    profile_ids = {row["profile_id"] for row in plan["profiles"]}

    assert plan["status"] == "planned"
    assert "db" in kr_smoke.KOREAN_CONNECTORS
    assert plan["allow_broker_calls_required"] is True
    assert {
        "kis-paper-sdk",
        "kis-live-sdk-readonly",
        "ls-paper-sdk",
        "ls-live-sdk-readonly",
        "kiwoom-paper-sdk",
        "kiwoom-live-sdk-readonly",
        "kiwoom-openapi-live-bridge-readonly",
        "daishin-cybos-live-bridge-readonly",
    } <= profile_ids
    assert "kis-live-trade" not in profile_ids
    assert "orders.place" not in {operation for row in plan["profiles"] for operation in row["operations"]}
    assert all(row["readonly"] is True for row in plan["profiles"])


def test_korean_smoke_runner_refuses_broker_calls_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("smoke runner should not touch a broker without explicit opt-in")

    monkeypatch.setattr(kr_smoke.service, "check_connection", fail)

    result = kr_smoke.run_smoke(profile_ids=["kis-paper-sdk"])

    assert result["status"] == "not_run"
    assert "allow_broker_calls=True" in result["reason"]
    assert result["profiles"][0]["profile_id"] == "kis-paper-sdk"
    assert result["profiles"][0]["status"] == "not_run"


def test_korean_smoke_runner_requires_live_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("live broker smoke should require allow_live=True")

    monkeypatch.setattr(kr_smoke.service, "check_connection", fail)

    result = kr_smoke.run_smoke(profile_ids=["kis-live-sdk-readonly"], allow_broker_calls=True)

    assert result["status"] == "blocked"
    assert "allow_live=True" in result["reason"]
    assert result["profiles"][0]["status"] == "blocked"


def test_korean_smoke_runner_executes_readonly_steps_with_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_check(profile_id: str):
        calls.append(("check", profile_id))
        return {"status": "ok", "profile_id": profile_id}

    def fake_quote(symbol: str, profile_id: str):
        calls.append(("quote", f"{profile_id}:{symbol}"))
        return {"status": "ok", "profile_id": profile_id, "symbol": symbol}

    monkeypatch.setattr(kr_smoke.service, "check_connection", fake_check)
    monkeypatch.setattr(kr_smoke.service, "get_quote", fake_quote)

    result = kr_smoke.run_smoke(
        profile_ids=["kis-paper-sdk"],
        operations=("check", "quote"),
        allow_broker_calls=True,
    )

    assert result["status"] == "ok"
    assert calls == [("check", "kis-paper-sdk"), ("quote", "kis-paper-sdk:005930")]
    assert result["profiles"][0]["steps"] == [
        {"operation": "check", "status": "ok", "profile_id": "kis-paper-sdk"},
        {"operation": "quote", "status": "ok", "profile_id": "kis-paper-sdk", "symbol": "005930"},
    ]


def test_trading_kr_smoke_tool_is_registered_and_defaults_to_plan_only() -> None:
    registry = build_registry()

    assert "trading_kr_smoke" in registry.tool_names
    assert TradingKoreanSmokeTool.is_readonly is True

    payload = TradingKoreanSmokeTool().execute(profile_ids=["kis-paper-sdk"])

    assert '"status": "not_run"' in payload
    assert "allow_broker_calls=True" in payload


def test_trading_kr_smoke_tool_passes_explicit_readonly_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_check(profile_id: str):
        calls.append(("check", profile_id))
        return {"status": "ok", "profile_id": profile_id}

    monkeypatch.setattr(kr_smoke.service, "check_connection", fake_check)

    payload = TradingKoreanSmokeTool().execute(
        profile_ids=["kis-paper-sdk"],
        operations=["check"],
        allow_broker_calls=True,
    )

    assert '"status": "ok"' in payload
    assert calls == [("check", "kis-paper-sdk")]
