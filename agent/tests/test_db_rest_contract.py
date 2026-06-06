"""DB Securities official REST OpenAPI contract tests.

These tests pin the DB Securities Open API portal JSON surface verified for
this Korean-market port. They use a fake client, so no live credentials or
network access are required.
"""

from __future__ import annotations

import importlib
from urllib.parse import urlparse

import pytest

from src.trading.connectors.kr_common import KoreanConnectorConfig

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _DbClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, params=None, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "params": params or {}, "json": json, "headers": headers or {}})
        if path == "/oauth2/token":
            return _Response({"access_token": "token-db", "scope": "oob", "token_type": "Bearer", "expires_in": 86400})
        if path == "/api/v1/quote/kr-stock/inquiry/price":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "rsp_msg": "정상 처리 되었습니다.",
                    "Out": {
                        "Prpr": "55550",
                        "PrdyVrss": "1650",
                        "PrdyCtrt": "3.06",
                        "AcmlVol": "7240324",
                        "Oprc": "54300",
                        "Hprc": "55900",
                        "Lprc": "54200",
                    },
                }
            )
        if path == "/api/v1/quote/overseas-stock/inquiry/price":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "rsp_msg": "정상 처리 되었습니다.",
                    "Out": {
                        "Sdpr": "207.8200",
                        "Prpr": "207.8200",
                        "Oprc": "207.8200",
                        "Hprc": "207.8200",
                        "Lprc": "207.8200",
                        "PrdyVrss": "0.0000",
                        "PrdyCtrt": "0.00",
                        "Per": "32.430",
                        "AcmlTrPbmn": "0",
                        "AcmlVol": "0",
                        "prdyVol": "78788867",
                        "bidp1": "0.0000",
                        "askp1": "0.0000",
                    },
                }
            )
        if path == "/api/v1/trading/kr-stock/inquiry/balance":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "rsp_msg": "조회가 완료되었습니다.",
                    "Out": {"DpsastAmt": 382955293, "TotEvalAmt": 79081550, "TotEvalPnlAmt": -7438651},
                    "Out1": [
                        {
                            "IsuNo": "A005930",
                            "IsuNm": "삼성전자",
                            "BalQty0": 540,
                            "AbleQty": 540,
                            "NowPrc": "75300.00",
                            "EvalAmt": 40662000,
                            "PchsAmt": 42299111,
                        }
                    ],
                }
            )
        if path == "/api/v1/trading/kr-stock/inquiry/transaction-history":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "rsp_msg": "조회가 완료되었습니다.",
                    "Out1": [
                        {
                            "OrdNo": 1356,
                            "OrgOrdNo": 0,
                            "IsuNo": "A004410",
                            "BnsTpCode": "2",
                            "OrdQty": 10,
                            "OrdPrc": "155.00",
                            "AllExecQty": 1,
                            "MrcAbleQty": 9,
                            "TrxTime": "102249011",
                        }
                    ],
                }
            )
        if path == "/api/v1/trading/kr-stock/order":
            return _Response({"rsp_cd": "00000", "rsp_msg": "매수 주문이 완료되었습니다.", "Out": {"OrdNo": 5633, "ShtnIsuNo": "A005930"}})
        if path == "/api/v1/trading/kr-stock/order-revision":
            return _Response({"rsp_cd": "00000", "rsp_msg": "정정주문이 완료되었습니다.", "Out": {"OrdNo": 14405, "PrntOrdNo": 14404}})
        if path == "/api/v1/trading/kr-stock/order-cancel":
            return _Response({"rsp_cd": "00000", "rsp_msg": "취소주문이 완료되었습니다.", "Out": {"OrdNo": 14417, "PrntOrdNo": 14414}})
        if path == "/api/v1/trading/kr-stock/order-nxt":
            return _Response({"rsp_cd": "00000", "rsp_msg": "매수 주문이 완료되었습니다.", "Out": {"OrdNo": 340807, "ShtnIsuNo": "A003620"}})
        if path == "/api/v1/trading/overseas-stock/order":
            return _Response({"rsp_cd": "00000", "rsp_msg": "매수 주문이 완료되었습니다.", "Out": {"OrdNo": 14}})
        if path == "/api/v1/trading/kr-stock/order-revision-nxt":
            return _Response({"rsp_cd": "00000", "rsp_msg": "정정주문이 완료되었습니다.", "Out": {"OrdNo": 340809, "PrntOrdNo": 340807}})
        if path == "/api/v1/trading/kr-stock/order-cancel-nxt":
            return _Response({"rsp_cd": "00000", "rsp_msg": "취소주문이 완료되었습니다.", "Out": {"OrdNo": 340811, "PrntOrdNo": 340807}})
        if path == "/api/v1/websocket/disconnectSession":
            return _Response({"acntNo": "11122333344", "result": "접속중인 세션이 초기화 되었습니다."})
        raise AssertionError(f"unexpected DB POST {path}")


def _db():
    return importlib.import_module("src.trading.connectors.db.sdk")


def _db_cfg(profile="paper") -> KoreanConnectorConfig:
    db = _db()
    return KoreanConnectorConfig(connector="db", profile=profile, app_key="app-key", app_secret="app-secret", paper_url=db.PAPER_URL, live_url=db.LIVE_URL)


def _call(client: _DbClient, path: str) -> dict:
    for call in client.calls:
        if call["path"] == path:
            return call
    raise AssertionError(f"missing DB call path={path}")


def test_db_catalog_matches_official_openapi_portal() -> None:
    db = _db()
    assert db.DB_OPENAPI_ENDPOINTS["auth_token"]["path"] == "/oauth2/token"
    assert db.DB_OPENAPI_ENDPOINTS["auth_token"]["content_type"] == "application/x-www-form-urlencoded"
    assert db.DB_OPENAPI_ENDPOINTS["stock_quote"]["path"] == "/api/v1/quote/kr-stock/inquiry/price"
    assert db.DB_OPENAPI_ENDPOINTS["stock_quote"]["tr_code"] == "PRICE"
    assert db.DB_OPENAPI_ENDPOINTS["account_balance"]["path"] == "/api/v1/trading/kr-stock/inquiry/balance"
    assert db.DB_OPENAPI_ENDPOINTS["account_balance"]["tr_code"] == "CSPAQ03420"
    assert db.DB_OPENAPI_ENDPOINTS["open_orders"]["path"] == "/api/v1/trading/kr-stock/inquiry/transaction-history"
    assert db.DB_OPENAPI_ENDPOINTS["open_orders"]["tr_code"] == "CSPAQ04800"
    assert db.DB_OPENAPI_ENDPOINTS["stock_order"]["path"] == "/api/v1/trading/kr-stock/order"
    assert db.DB_OPENAPI_ENDPOINTS["stock_order"]["tr_code"] == "CSPAT00600"
    assert db.DB_OPENAPI_ENDPOINTS["modify_order"]["path"] == "/api/v1/trading/kr-stock/order-revision"
    assert db.DB_OPENAPI_ENDPOINTS["modify_order"]["tr_code"] == "CSPAT00700"
    assert db.DB_OPENAPI_ENDPOINTS["cancel_order"]["path"] == "/api/v1/trading/kr-stock/order-cancel"
    assert db.DB_OPENAPI_ENDPOINTS["cancel_order"]["tr_code"] == "CSPAT00800"
    assert db.DB_OPENAPI_ENDPOINTS["stock_order_nxt"]["path"] == "/api/v1/trading/kr-stock/order-nxt"
    assert db.DB_OPENAPI_ENDPOINTS["stock_order_nxt"]["tr_code"] == "CSPAT00610"
    assert db.DB_OPENAPI_ENDPOINTS["modify_order_nxt"]["path"] == "/api/v1/trading/kr-stock/order-revision-nxt"
    assert db.DB_OPENAPI_ENDPOINTS["modify_order_nxt"]["tr_code"] == "CSPAT00710"
    assert db.DB_OPENAPI_ENDPOINTS["cancel_order_nxt"]["path"] == "/api/v1/trading/kr-stock/order-cancel-nxt"
    assert db.DB_OPENAPI_ENDPOINTS["cancel_order_nxt"]["tr_code"] == "CSPAT00810"
    assert db.DB_OPENAPI_ENDPOINTS["overseas_stock_quote"]["path"] == "/api/v1/quote/overseas-stock/inquiry/price"
    assert db.DB_OPENAPI_ENDPOINTS["overseas_stock_quote"]["tr_code"] == "FSTKPRICE"
    assert db.DB_OPENAPI_ENDPOINTS["overseas_stock_order"]["path"] == "/api/v1/trading/overseas-stock/order"
    assert db.DB_OPENAPI_ENDPOINTS["overseas_stock_order"]["tr_code"] == "CAZCT00100"


def test_db_overseas_stock_operations_are_classified_read_write() -> None:
    from src.live.classification import ToolClass
    from src.trading.connectors.db.classification import DB_TOOL_CLASS

    assert DB_TOOL_CLASS["overseas_stock_quote"] is ToolClass.READ
    assert DB_TOOL_CLASS["overseas_stock_order"] is ToolClass.WRITE


def test_db_websocket_catalog_matches_official_openapi_portal() -> None:
    db = _db()
    assert db.DB_WEBSOCKET_URLS == {
        "paper": "wss://openapi.dbsec.co.kr:17070",
        "live": "wss://openapi.dbsec.co.kr:7070",
    }
    assert db.DB_WEBSOCKET_CHANNELS["trade"]["path"] == "/pub/S00"
    assert db.DB_WEBSOCKET_CHANNELS["trade"]["tr_code"] == "S00"
    assert db.DB_WEBSOCKET_CHANNELS["trade"]["tr_type"] == "1"
    assert db.DB_WEBSOCKET_CHANNELS["orderbook"]["path"] == "/pub/S01"
    assert db.DB_WEBSOCKET_CHANNELS["orderbook"]["tr_code"] == "S01"
    assert db.DB_WEBSOCKET_CHANNELS["order_accept"]["path"] == "/pub/IS0"
    assert db.DB_WEBSOCKET_CHANNELS["order_accept"]["tr_type"] == "3"
    assert db.DB_WEBSOCKET_CHANNELS["order_execution"]["path"] == "/pub/IS1"
    assert db.DB_WEBSOCKET_CHANNELS["order_execution"]["tr_code"] == "IS1"
    assert db.DB_OPENAPI_ENDPOINTS["websocket_disconnect_session"]["path"] == "/api/v1/websocket/disconnectSession"
    assert db.DB_OPENAPI_ENDPOINTS["websocket_disconnect_session"]["tr_code"] == "DisconnectSession"


def test_db_websocket_messages_use_official_s00_s01_and_is1_contracts() -> None:
    db = _db()
    cfg = _db_cfg().with_overrides(access_token="token-db")
    assert db.websocket_url(cfg) == "wss://openapi.dbsec.co.kr:17070"
    assert db.websocket_url(_db_cfg(profile="live-readonly")) == "wss://openapi.dbsec.co.kr:7070"

    assert db.build_websocket_subscribe_message("005930.KS", channel="trade", config=cfg) == {
        "header": {"token": "token-db", "tr_type": "1"},
        "body": {"tr_cd": "S00", "tr_key": "J 005930"},
    }
    assert db.build_websocket_subscribe_message("KRX:005930", channel="orderbook", config=cfg) == {
        "header": {"token": "token-db", "tr_type": "1"},
        "body": {"tr_cd": "S01", "tr_key": "J 005930"},
    }
    assert db.build_websocket_subscribe_message("", channel="order_execution", config=cfg) == {
        "header": {"token": "token-db", "tr_type": "3"},
        "body": {"tr_cd": "IS1"},
    }


def test_db_websocket_message_parser_normalizes_trade_and_orderbook_events() -> None:
    db = _db()
    trade = db.parse_websocket_message(
        {
            "header": {"tr_cd": "S00", "tr_key": None},
            "body": {
                "ShrnIscd": "U-005930",
                "StckPrpr": "143300",
                "PrdyVrss": "33000",
                "PrdyCtrt": "29.92",
                "StckOprc": "140000",
                "StckHgpr": "143300",
                "StckLwpr": "77300",
                "CntgVol": "100",
                "AcmlVol": "405039",
                "Askp1": "140200",
                "Bidp1": "143300",
            },
        }
    )
    orderbook = db.parse_websocket_message(
        {
            "header": {"tr_cd": "S01", "tr_key": None},
            "body": {
                "ShrnIscd": "005930",
                "Askp1": "54500",
                "Bidp1": "54400",
                "AskpRsqn1": "154160",
                "BidpRsqn1": "126822",
                "TotalAskprsqn": "809630",
                "TotalBidprsqn": "2193305",
            },
        }
    )

    assert trade["status"] == "ok"
    assert trade["channel"] == "trade"
    assert trade["symbol"] == "005930"
    assert trade["quote"]["last"] == 143300.0
    assert trade["quote"]["change_rate"] == 29.92
    assert trade["quote"]["trade_volume"] == 100.0
    assert orderbook["status"] == "ok"
    assert orderbook["channel"] == "orderbook"
    assert orderbook["symbol"] == "005930"
    assert orderbook["orderbook"]["asks"][0] == {"price": 54500.0, "quantity": 154160.0}
    assert orderbook["orderbook"]["bids"][0] == {"price": 54400.0, "quantity": 126822.0}


def test_db_websocket_disconnect_session_uses_official_rest_contract() -> None:
    db = _db()
    client = _DbClient()
    out = db.disconnect_websocket_sessions(_db_cfg(), client=client)

    assert out["status"] == "ok"
    call = _call(client, "/api/v1/websocket/disconnectSession")
    assert call["json"] == {}
    assert call["headers"]["authorization"] == "Bearer token-db"


def test_db_quote_requests_token_and_official_price_contract() -> None:
    db = _db()
    client = _DbClient()
    out = db.get_quote("005930.KS", config=_db_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "005930"
    assert out["quote"]["last"] == 55550.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/token"
    assert token_call["params"] == {"appkey": "app-key", "appsecretkey": "app-secret", "grant_type": "client_credentials", "scope": "oob"}
    assert token_call["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert quote_call["path"] == "/api/v1/quote/kr-stock/inquiry/price"
    assert quote_call["headers"] == {
        "content-type": "application/json; charset=utf-8",
        "authorization": "Bearer token-db",
        "cont_yn": "N",
        "cont_key": "",
    }
    assert quote_call["json"] == {"In": {"InputIscd1": "005930", "InputCondMrktDivCode": "J"}}


def test_db_overseas_quote_uses_official_fstkprice_contract() -> None:
    db = _db()
    client = _DbClient()
    out = db.get_overseas_quote("TSLA.US", config=_db_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "TSLA"
    assert out["market_code"] == "FN"
    assert out["quote"]["last"] == 207.82
    assert out["quote"]["previous_close"] == 207.82
    assert out["quote"]["per"] == 32.43

    quote_call = _call(client, "/api/v1/quote/overseas-stock/inquiry/price")
    assert quote_call["headers"]["authorization"] == "Bearer token-db"
    assert quote_call["json"] == {"In": {"InputIscd1": "TSLA", "InputCondMrktDivCode": "FN"}}


def test_db_account_and_open_orders_use_official_inquiry_contracts() -> None:
    db = _db()
    client = _DbClient()
    snapshot = db.get_account_snapshot(_db_cfg(), client=client)
    orders = db.get_open_orders(_db_cfg(), client=client)
    assert snapshot["status"] == "ok"
    assert snapshot["account"]["cash"] == 382955293.0
    assert snapshot["positions"][0]["symbol"] == "005930"
    assert orders["status"] == "ok"
    assert orders["orders"][0]["order_id"] == "1356"
    assert orders["orders"][0]["remaining_quantity"] == 9.0

    balance_call = _call(client, "/api/v1/trading/kr-stock/inquiry/balance")
    open_orders_call = _call(client, "/api/v1/trading/kr-stock/inquiry/transaction-history")
    assert balance_call["json"] == {"In": {"QryTpCode0": "0"}}
    assert open_orders_call["json"] == {
        "In": {"ExecYn": "0", "BnsTpCode": "0", "IsuTpCode": "0", "QryTp": "0", "TrdMktCode": "0", "SorTpYn": "2"}
    }


def test_db_order_modify_and_cancel_use_official_stock_order_contracts() -> None:
    db = _db()
    client = _DbClient()
    order = db.place_order(_db_cfg(), symbol="005930", side="buy", quantity=1, order_type="market", client=client)
    modified = db.modify_order(_db_cfg(), "14404", symbol="005930", quantity=5, limit_price=80000, client=client)
    cancelled = db.cancel_order(_db_cfg(), "14414", symbol="005930", quantity=10, client=client)
    assert order["status"] == "ok"
    assert order["order_id"] == "5633"
    assert modified["status"] == "ok"
    assert cancelled["status"] == "ok"

    order_call = _call(client, "/api/v1/trading/kr-stock/order")
    modify_call = _call(client, "/api/v1/trading/kr-stock/order-revision")
    cancel_call = _call(client, "/api/v1/trading/kr-stock/order-cancel")
    assert order_call["json"] == {
        "In": {
            "IsuNo": "005930",
            "OrdQty": 1,
            "OrdPrc": 0,
            "BnsTpCode": "2",
            "OrdprcPtnCode": "03",
            "MgntrnCode": "000",
            "LoanDt": "00000000",
            "OrdCndiTpCode": "0",
            "TrchNo": 1,
        }
    }
    assert modify_call["json"] == {
        "In": {"OrgOrdNo": 14404, "IsuNo": "A005930", "OrdQty": 5, "OrdprcPtnCode": "00", "OrdCndiTpCode": "0", "OrdPrc": 80000}
    }
    assert cancel_call["json"] == {"In": {"OrgOrdNo": 14414, "IsuNo": "A005930", "OrdQty": 10}}


def test_db_nxt_order_modify_and_cancel_use_official_nxt_contracts() -> None:
    db = _db()
    client = _DbClient()
    order = db.place_order(
        _db_cfg(),
        symbol="003620",
        side="buy",
        quantity=20,
        order_type="limit",
        limit_price=3010,
        client=client,
        exchange="NXT",
    )
    modified = db.modify_order(_db_cfg(), "340808", symbol="003620", quantity=20, limit_price=4370, client=client, exchange="NXT")
    cancelled = db.cancel_order(_db_cfg(), "340809", symbol="003620", quantity=19, client=client, exchange="NXT")
    assert order["status"] == "ok"
    assert order["order_id"] == "340807"
    assert modified["status"] == "ok"
    assert cancelled["status"] == "ok"

    order_call = _call(client, "/api/v1/trading/kr-stock/order-nxt")
    modify_call = _call(client, "/api/v1/trading/kr-stock/order-revision-nxt")
    cancel_call = _call(client, "/api/v1/trading/kr-stock/order-cancel-nxt")
    assert order_call["json"] == {
        "In": {
            "IsuNo": "003620",
            "OrdQty": 20,
            "OrdPrc": 3010,
            "BnsTpCode": "2",
            "OrdprcPtnCode": "00",
            "MgntrnCode": "000",
            "LoanDt": "00000000",
            "OrdCndiTpCode": "0",
        }
    }
    assert modify_call["json"] == {
        "In": {"OrgOrdNo": 340808, "IsuNo": "A003620", "OrdQty": 20, "OrdprcPtnCode": "00", "OrdCndiTpCode": "0", "OrdPrc": 4370}
    }
    assert cancel_call["json"] == {"In": {"OrgOrdNo": 340809, "IsuNo": "A003620", "OrdQty": 19}}


def test_db_overseas_stock_order_uses_official_cazct00100_contract() -> None:
    db = _db()
    client = _DbClient()
    order = db.place_overseas_stock_order(
        _db_cfg(),
        symbol="SOXL.US",
        side="buy",
        quantity=1,
        order_type="market",
        client=client,
    )
    assert order["status"] == "ok"
    assert order["symbol"] == "SOXL"
    assert order["order_id"] == "14"
    assert order["order_type"] == "market"

    order_call = _call(client, "/api/v1/trading/overseas-stock/order")
    assert order_call["json"] == {
        "In": {
            "AstkIsuNo": "SOXL",
            "AstkBnsTpCode": "2",
            "AstkOrdprcPtnCode": "2",
            "AstkOrdCndiTpCode": "1",
            "AstkOrdQty": 1,
            "AstkOrdPrc": 0,
            "OrdTrdTpCode": "0",
            "OrgOrdNo": 0,
        }
    }


def test_db_overseas_order_is_explicit_and_not_generic_domestic_order() -> None:
    db = _db()
    client = _DbClient()
    generic = db.place_order(_db_cfg(), symbol="SOXL.US", side="buy", quantity=1, order_type="market", client=client)
    assert generic["status"] == "error"
    assert "use place_overseas_stock_order" in generic["error"]
