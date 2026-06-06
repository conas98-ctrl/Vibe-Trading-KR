"""Toss Securities Open API REST contract tests."""

from __future__ import annotations

from typing import Any

import pytest

from src.live.classification import ToolClass
from src.live.mandate.model import AssetClass, InstrumentType
from src.trading import profiles, service
from src.trading.connectors.toss import sdk as toss

pytestmark = pytest.mark.unit


def _configured_toss() -> toss.KoreanConnectorConfig:
    return toss.build_config(
        {"profile": "paper"},
        {
            "app_key": "c_test",
            "app_secret": "s_test",
            "account": "7",
            "base_url": "https://openapi.tossinvest.com",
        },
    )


def _capture_requests(monkeypatch: pytest.MonkeyPatch, responses: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    queue = list(responses or [])

    def fake_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/oauth2/token"):
            return {"access_token": "test-token", "expires_in": 3600, "token_type": "Bearer"}
        if queue:
            return queue.pop(0)
        return {"result": {}}

    monkeypatch.setattr(toss, "_request_json", fake_request)
    return calls


def test_toss_profiles_are_registered_and_classified() -> None:
    ids = {p.id for p in profiles.list_profiles()}
    assert {
        "toss-paper-sdk",
        "toss-live-sdk-readonly",
        "toss-paper-trade",
        "toss-live-trade",
    } <= ids

    paper = profiles.profile_by_id("toss-paper-sdk")
    live = profiles.profile_by_id("toss-live-trade")
    assert paper.connector == "toss"
    assert paper.transport == "broker_sdk"
    assert paper.readonly is True
    assert live.connector == "toss"
    assert live.transport == "broker_sdk"
    assert live.readonly is False
    assert "orders.place.requires_mandate" in live.capabilities

    kr_instrument, kr_asset = service._order_classification("toss", "005930")
    us_instrument, us_asset = service._order_classification("toss", "AAPL")
    assert kr_instrument is InstrumentType.EQUITY
    assert kr_asset is AssetClass.KR_EQUITY
    assert us_instrument is InstrumentType.EQUITY
    assert us_asset is AssetClass.US_EQUITY


def test_toss_connector_degrades_cleanly_when_unconfigured(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(toss, "get_runtime_root", lambda: tmp_path, raising=False)

    result = service.check_connection("toss-paper-sdk")

    assert result["status"] == "error"
    assert result["connector"] == "toss"
    assert "not configured" in result["error"].lower()


def test_toss_read_write_classification_map() -> None:
    from src.trading.connectors.toss.classification import TOSS_TOOL_CLASS

    assert TOSS_TOOL_CLASS["get_prices"] is ToolClass.READ
    assert TOSS_TOOL_CLASS["get_holdings"] is ToolClass.READ
    assert TOSS_TOOL_CLASS["create_order"] is ToolClass.WRITE
    assert TOSS_TOOL_CLASS["modify_order"] is ToolClass.WRITE
    assert TOSS_TOOL_CLASS["cancel_order"] is ToolClass.WRITE


def test_toss_quote_uses_oauth_and_prices_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [{"result": [{"symbol": "005930", "lastPrice": "72000", "currency": "KRW"}]}],
    )

    result = toss.get_quote("005930", config=_configured_toss())

    assert result["status"] == "ok"
    assert result["quote"]["symbol"] == "005930"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "https://openapi.tossinvest.com/oauth2/token"
    assert calls[0]["form"] == {
        "grant_type": "client_credentials",
        "client_id": "c_test",
        "client_secret": "s_test",
    }
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"] == "https://openapi.tossinvest.com/api/v1/prices"
    assert calls[1]["params"] == {"symbols": "005930"}
    assert calls[1]["headers"]["Authorization"] == "Bearer test-token"


def test_toss_positions_use_account_header(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [
            {
                "result": {
                    "items": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc.",
                            "marketCountry": "US",
                            "currency": "USD",
                            "quantity": "10",
                        }
                    ]
                }
            }
        ],
    )

    result = toss.get_positions(_configured_toss())

    assert result["status"] == "ok"
    assert result["positions"][0]["symbol"] == "AAPL"
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"] == "https://openapi.tossinvest.com/api/v1/holdings"
    assert calls[1]["headers"]["Authorization"] == "Bearer test-token"
    assert calls[1]["headers"]["X-Tossinvest-Account"] == "7"


def test_toss_place_modify_and_cancel_order_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [
            {"result": {"orderId": "ord-1", "clientOrderId": "client-1"}},
            {"result": {"orderId": "ord-1", "clientOrderId": "client-1"}},
            {"result": {"orderId": "ord-1", "clientOrderId": "client-1"}},
        ],
    )
    cfg = _configured_toss()

    placed = toss.place_order(
        cfg,
        symbol="005930",
        side="buy",
        quantity=10,
        order_type="limit",
        limit_price=70000,
        client_order_id="client-1",
    )
    modified = toss.modify_order(cfg, "ord-1", order_type="limit", quantity=15, limit_price=71000)
    cancelled = toss.cancel_order(cfg, "ord-1")

    assert placed["status"] == "ok"
    assert modified["status"] == "ok"
    assert cancelled["status"] == "ok"
    order_calls = [call for call in calls if call["url"].endswith(("/api/v1/orders", "/api/v1/orders/ord-1/modify", "/api/v1/orders/ord-1/cancel"))]
    assert order_calls[0]["method"] == "POST"
    assert order_calls[0]["json_body"] == {
        "clientOrderId": "client-1",
        "symbol": "005930",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "10",
        "price": "70000",
    }
    assert order_calls[0]["headers"]["X-Tossinvest-Account"] == "7"
    assert order_calls[1]["json_body"] == {"orderType": "LIMIT", "quantity": "15", "price": "71000"}
    assert order_calls[2]["json_body"] == {}


def test_toss_order_detail_uses_account_header(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [
            {
                "result": {
                    "orderId": "ord-1",
                    "symbol": "005930",
                    "status": "FILLED",
                    "execution": {"filledQuantity": "10", "averageFilledPrice": "70000"},
                }
            }
        ],
    )

    result = toss.get_order(_configured_toss(), "ord-1")

    assert result["status"] == "ok"
    assert result["order"]["orderId"] == "ord-1"
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"] == "https://openapi.tossinvest.com/api/v1/orders/ord-1"
    assert calls[1]["headers"]["Authorization"] == "Bearer test-token"
    assert calls[1]["headers"]["X-Tossinvest-Account"] == "7"


def test_toss_order_info_endpoints_use_account_header_and_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [
            {"result": {"currency": "KRW", "cashBuyingPower": "5000000"}},
            {"result": {"sellableQuantity": "100"}},
            {
                "result": [
                    {"marketCountry": "KR", "commissionRate": "0.015"},
                    {"marketCountry": "US", "commissionRate": "0.1"},
                ]
            },
        ],
    )
    cfg = _configured_toss()

    buying_power = toss.get_buying_power(cfg, currency="KRW")
    sellable = toss.get_sellable_quantity(cfg, symbol="005930")
    commissions = toss.get_commissions(cfg)

    assert buying_power["status"] == "ok"
    assert buying_power["cash_buying_power"] == "5000000"
    assert sellable["sellable_quantity"] == "100"
    assert commissions["commissions"][0]["marketCountry"] == "KR"

    info_calls = [
        call
        for call in calls
        if call["url"].endswith(("/api/v1/buying-power", "/api/v1/sellable-quantity", "/api/v1/commissions"))
    ]
    assert [call["method"] for call in info_calls] == ["GET", "GET", "GET"]
    assert info_calls[0]["params"] == {"currency": "KRW"}
    assert info_calls[1]["params"] == {"symbol": "005930"}
    assert info_calls[2]["params"] == {}
    assert all(call["headers"]["X-Tossinvest-Account"] == "7" for call in info_calls)


def test_toss_history_uses_candles_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_requests(
        monkeypatch,
        [
            {
                "result": {
                    "candles": [
                        {
                            "timestamp": "2026-03-25T09:00:00+09:00",
                            "openPrice": "71600",
                            "highPrice": "72300",
                            "lowPrice": "71500",
                            "closePrice": "72000",
                            "volume": "3521000",
                            "currency": "KRW",
                        }
                    ],
                    "nextBefore": None,
                }
            }
        ],
    )

    result = toss.get_historical_bars("005930", config=_configured_toss(), period="1d", limit=1)

    assert result["status"] == "ok"
    assert result["bars"][0]["close"] == "72000"
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"] == "https://openapi.tossinvest.com/api/v1/candles"
    assert calls[1]["params"] == {"symbol": "005930", "interval": "1d", "count": 1, "adjusted": True}
