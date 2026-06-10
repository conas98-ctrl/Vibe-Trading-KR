"""Order-path enforcement of profile capabilities and token caching."""

from __future__ import annotations

from typing import Any

import pytest

from src.trading import service
from src.trading.connectors import kr_common
from src.trading.connectors.kis import sdk as kis_sdk
from src.trading.connectors.kr_common import KoreanConnectorConfig


class _ExplodingModule:
    """Stand-in SDK module that fails the test if the order path reaches it."""

    def build_config(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def place_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("place_order must not be reached for read-only profiles")

    def cancel_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("cancel_order must not be reached for read-only profiles")


@pytest.fixture(autouse=True)
def _no_sdk_calls(monkeypatch):
    monkeypatch.setattr(service, "_sdk_module", lambda connector: _ExplodingModule())


@pytest.mark.parametrize(
    "profile_id",
    ["kis-paper-sdk", "kis-live-sdk-readonly", "ls-paper-sdk", "db-paper-sdk", "kiwoom-paper-sdk"],
)
def test_place_order_denied_for_readonly_profiles(profile_id):
    result = service.place_order("005930", profile_id, side="buy", quantity=1)
    assert result["status"] == "error"
    assert "orders.place" in result["error"]


@pytest.mark.parametrize("profile_id", ["kis-paper-sdk", "kis-live-sdk-readonly"])
def test_cancel_order_denied_for_readonly_profiles(profile_id):
    result = service.cancel_order("12345:67890", profile_id)
    assert result["status"] == "error"
    assert "orders.cancel" in result["error"]


def test_place_order_allowed_for_trade_capable_paper_profile(monkeypatch):
    calls: list[dict[str, Any]] = []

    class _Recorder(_ExplodingModule):
        def place_order(self, config: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"status": "ok"}

    monkeypatch.setattr(service, "_sdk_module", lambda connector: _Recorder())
    result = service.place_order("005930", "kis-paper-trade", side="buy", quantity=1)
    assert result["status"] == "ok"
    assert len(calls) == 1


def test_bare_six_digit_symbol_only_maps_to_kr_for_toss():
    from src.live.mandate.model import AssetClass

    _, toss_class = service._order_classification("toss", "005930")
    assert toss_class is AssetClass.KR_EQUITY
    _, futu_class = service._order_classification("futu", "600519")
    assert futu_class is None
    _, futu_kr = service._order_classification("futu", "005930.KS")
    assert futu_kr is AssetClass.KR_EQUITY


class _CountingClient:
    """Fake httpx-style client counting auth-token issuance."""

    def __init__(self) -> None:
        self.auth_calls = 0

    def post(self, url: str, **kwargs: Any) -> Any:
        self.auth_calls += 1
        client = self

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {"access_token": f"token-{client.auth_calls}", "expires_in": 86400}

        return _Response()


def test_kis_access_token_issued_once_per_credentials():
    config = KoreanConnectorConfig(
        connector="kis", profile="paper", app_key="pk-app", app_secret="pk-secret", paper_url="https://paper.test"
    )
    client = _CountingClient()
    first = kis_sdk._access_token(config, client)
    second = kis_sdk._access_token(config, client)
    assert first == second == "token-1"
    assert client.auth_calls == 1


def test_token_cache_expires_and_reissues(monkeypatch):
    config = KoreanConnectorConfig(
        connector="kis", profile="paper", app_key="pk-app", app_secret="pk-secret", paper_url="https://paper.test"
    )
    client = _CountingClient()
    kis_sdk._access_token(config, client)

    real_monotonic = kr_common.time.monotonic
    monkeypatch.setattr(kr_common.time, "monotonic", lambda: real_monotonic() + 90000.0)
    token = kis_sdk._access_token(config, client)
    assert token == "token-2"
    assert client.auth_calls == 2


def test_explicit_config_token_bypasses_cache():
    config = KoreanConnectorConfig(connector="kis", profile="paper", access_token="user-supplied")
    client = _CountingClient()
    assert kis_sdk._access_token(config, client) == "user-supplied"
    assert client.auth_calls == 0
