"""LS and Kiwoom official REST/WebSocket contract tests.

These tests pin the Korean broker REST paths, WebSocket endpoints, headers, and
body fields found in the official LS OpenAPI and Kiwoom OpenAPI guides. They
use fake clients so they do not require live credentials or network calls.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

import pytest

from src.tools.trading_connector_tool import TradingLsWebSocketChannelsTool
from src.trading.connectors.kiwoom import sdk as kiwoom
from src.trading.connectors.kr_common import KoreanConnectorConfig, KoreanConnectorConfigError
from src.trading.connectors.ls import sdk as ls

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


class _LsClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, params=None, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "params": params or {}, "json": json, "headers": headers or {}})
        if path == "/oauth2/token":
            return _Response({"access_token": "token-ls", "token_type": "Bearer", "expires_in": 86400})
        if path == "/stock/market-data":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "t1101OutBlock": {
                        "shcode": "078020",
                        "price": 4545,
                        "change": 10,
                        "diff": "0.22",
                        "volume": 2702,
                    },
                }
            )
        if path == "/stock/accno":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "t0424OutBlock": {"sunamt": 203287854, "tappamt": 203287854},
                    "t0424OutBlock1": [
                        {"expcode": "249420", "janqty": 1091, "price": 16400, "mamt": 67730600, "hname": "일동제약"}
                    ],
                }
            )
        if path == "/stock/order":
            tr_cd = (headers or {}).get("tr_cd", "")
            if tr_cd == "CSPAT00601":
                return _Response({"rsp_cd": "00040", "rsp_msg": "buy order accepted", "CSPAT00601OutBlock2": {"OrdNo": 32004}})
            if tr_cd == "CSPAT00701":
                return _Response({"rsp_cd": "00000", "rsp_msg": "modify order accepted", "CSPAT00701OutBlock2": {"OrdNo": 32005}})
            if tr_cd == "CSPAT00801":
                return _Response({"rsp_cd": "00156", "rsp_msg": "cancel order accepted", "CSPAT00801OutBlock2": {"OrdNo": 84006}})
            raise AssertionError(f"unexpected LS stock/order tr_cd={tr_cd}")
        raise AssertionError(f"unexpected LS POST {path}")


class _LsSocket:
    def __init__(self):
        self.sent_json: list[dict] = []
        self.closed = False
        self.frames = [
            json.dumps(
                {
                    "header": {"tr_cd": "S3_", "tr_key": "005930"},
                    "body": {
                        "shcode": "005930",
                        "price": "70000",
                        "change": "1000",
                        "drate": "1.45",
                        "cvolume": "15",
                        "volume": "123456",
                        "chetime": "153000",
                    },
                }
            ),
            {
                "header": {"tr_cd": "HA_", "tr_key": "035720"},
                "body": {
                    "shcode": "035720",
                    "offerho1": "50000",
                    "offerrem1": "10",
                    "bidho1": "49950",
                    "bidrem1": "8",
                    "hotime": "090001",
                },
            },
        ]

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def receive(self):
        if not self.frames:
            raise AssertionError("no more LS WebSocket frames")
        return self.frames.pop(0)

    async def close(self):
        self.closed = True


class _LsTransport:
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _LsSocket()

    async def connect(self, url):
        self.urls.append(url)
        return self.socket


class _SubscriptionAckLsSocket(_LsSocket):
    def __init__(self):
        super().__init__()
        self.frames = [
            {
                "header": {"tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"},
                "body": {"rsp_cd": "00000", "rsp_msg": "SUBSCRIBE SUCCESS"},
            },
            json.dumps(
                {
                    "header": {"tr_cd": "S3_", "tr_key": "005930"},
                    "body": {
                        "shcode": "005930",
                        "price": "70000",
                        "change": "1000",
                        "drate": "1.45",
                        "cvolume": "15",
                        "volume": "123456",
                        "chetime": "153000",
                    },
                }
            ),
        ]


class _SubscriptionAckLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _SubscriptionAckLsSocket()


class _SubscriptionErrorLsSocket(_LsSocket):
    def __init__(self):
        super().__init__()
        self.frames = [
            {
                "header": {"tr_cd": "S3_", "tr_type": "3", "tr_key": "005930", "token": "token-ls"},
                "body": {"rsp_cd": "99999", "rsp_msg": "SUBSCRIBE DENIED"},
            }
        ]


class _SubscriptionErrorLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _SubscriptionErrorLsSocket()


class _MalformedFrameLsSocket(_LsSocket):
    def __init__(self):
        super().__init__()
        self.frames = ["malformed-frame"]


class _MalformedFrameLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _MalformedFrameLsSocket()


class _HangingLsSocket(_LsSocket):
    async def receive(self):
        await asyncio.sleep(1)


class _HangingLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _HangingLsSocket()


class _FlakyLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _LsSocket()
        self.failures_remaining = 1

    async def connect(self, url):
        self.urls.append(url)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise OSError("temporary connect failure")
        return self.socket


class _FailingLsTransport(_LsTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _LsSocket()

    async def connect(self, url):
        self.urls.append(url)
        raise OSError("temporary connect failure")


class _DisconnectingLsSocket(_LsSocket):
    async def receive(self):
        raise ConnectionError("socket dropped after subscribe")


class _ReconnectLsTransport:
    def __init__(self):
        self.urls: list[str] = []
        self.sockets: list[_LsSocket] = [_DisconnectingLsSocket(), _LsSocket()]
        self._index = 0

    async def connect(self, url):
        self.urls.append(url)
        socket = self.sockets[self._index]
        self._index += 1
        return socket


class _WebSocketClient:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False
        self.messages: list[str | dict] = [
            json.dumps({"header": {"tr_cd": "S3_", "tr_key": "005930"}, "body": {"shcode": "005930", "price": "70000"}})
        ]

    async def send(self, payload):
        self.sent.append(payload)

    async def recv(self):
        return self.messages.pop(0)

    async def close(self):
        self.closed = True


class _KiwoomClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        api_id = (headers or {}).get("api-id", "")
        self.calls.append({"method": "POST", "path": path, "json": json or {}, "headers": headers or {}})
        if path == "/oauth2/token":
            return _Response({"return_code": 0, "return_msg": "정상적으로 처리되었습니다", "token_type": "bearer", "token": "token-kw"})
        if path == "/api/dostk/stkinfo" and api_id == "ka10001":
            return _Response(
                {
                    "return_code": 0,
                    "stk_cd": "005930",
                    "cur_prc": "+70000",
                    "pred_pre": "+1000",
                    "flu_rt": "+1.45",
                    "trde_qty": "123456",
                    "open_pric": "+69000",
                    "high_pric": "+71000",
                    "low_pric": "+68000",
                }
            )
        if path == "/api/dostk/chart" and api_id == "ka10081":
            return _Response(
                {
                    "return_code": 0,
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {
                            "dt": "20260604",
                            "open_pric": "69000",
                            "high_pric": "71000",
                            "low_pric": "68000",
                            "cur_prc": "70000",
                            "trde_qty": "1000",
                        }
                    ],
                }
            )
        if path == "/api/dostk/acnt" and api_id == "kt00018":
            return _Response(
                {
                    "return_code": 0,
                    "tot_evlt_amt": "640000",
                    "prsm_dpst_aset_amt": "500000",
                    "acnt_evlt_remn_indv_tot": [
                        {"stk_cd": "A005930", "stk_nm": "삼성전자", "rmnd_qty": "2", "evlt_amt": "140000", "pur_pric": "69000"}
                    ],
                }
            )
        if path == "/api/dostk/acnt" and api_id == "ka10075":
            return _Response(
                {
                    "return_code": 0,
                    "oso": [{"ord_no": "1234567", "stk_cd": "005930", "ord_qty": "3", "ord_pric": "70000", "oso_qty": "1"}],
                }
            )
        if path == "/api/dostk/ordr" and api_id in {"kt10000", "kt10001", "kt10002", "kt10003"}:
            return _Response({"return_code": 0, "return_msg": "정상", "ord_no": "7654321", "dmst_stex_tp": "KRX"})
        raise AssertionError(f"unexpected Kiwoom POST {path} api-id={api_id}")


def _kiwoom_call(client: _KiwoomClient, api_id: str) -> dict:
    for call in client.calls:
        if call["headers"].get("api-id") == api_id:
            return call
    raise AssertionError(f"missing Kiwoom call api-id={api_id}")


def _ls_cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(connector="ls", profile=profile, app_key="app-key", app_secret="app-secret", paper_url=ls.PAPER_URL, live_url=ls.LIVE_URL)


def _kiwoom_cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(
        connector="kiwoom",
        profile=profile,
        app_key="app-key",
        app_secret="app-secret",
        paper_url=kiwoom.PAPER_URL,
        live_url=kiwoom.LIVE_URL,
    )


def test_ls_catalog_matches_official_openapi_samples() -> None:
    assert ls.LS_OPENAPI_ENDPOINTS["auth_token"]["path"] == "/oauth2/token"
    assert ls.LS_OPENAPI_ENDPOINTS["auth_token"]["content_type"] == "application/x-www-form-urlencoded"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_quote"]["path"] == "/stock/market-data"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_quote"]["tr_cd"] == "t1101"
    assert ls.LS_OPENAPI_ENDPOINTS["account_balance"]["path"] == "/stock/accno"
    assert ls.LS_OPENAPI_ENDPOINTS["account_balance"]["tr_cd"] == "t0424"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_order"]["path"] == "/stock/order"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_order"]["tr_cd"] == "CSPAT00601"
    assert ls.LS_OPENAPI_ENDPOINTS["modify_order"]["tr_cd"] == "CSPAT00701"
    assert ls.LS_OPENAPI_ENDPOINTS["cancel_order"]["tr_cd"] == "CSPAT00801"


def test_ls_websocket_catalog_matches_official_openapi_guide() -> None:
    assert ls.LS_WEBSOCKET_URLS == {
        "paper": "wss://openapi.ls-sec.co.kr:29443",
        "live": "wss://openapi.ls-sec.co.kr:9443",
    }
    assert ls.LS_WEBSOCKET_ENDPOINTS["stock_realtime"]["path"] == "/websocket/stock"
    assert ls.LS_WEBSOCKET_ENDPOINTS["stock_realtime"]["api_id"] == "9a2800c3-9bf2-4d67-8d83-905074f06646"
    assert len(ls.LS_STOCK_WEBSOCKET_TRS) == 65
    assert ls.LS_STOCK_WEBSOCKET_TRS["H1_"] == "KOSPI호가잔량"
    assert ls.LS_STOCK_WEBSOCKET_TRS["HA_"] == "KOSDAQ호가잔량"
    assert ls.LS_STOCK_WEBSOCKET_TRS["S3_"] == "KOSPI체결"
    assert ls.LS_STOCK_WEBSOCKET_TRS["K3_"] == "KOSDAQ체결"
    assert ls.LS_STOCK_WEBSOCKET_TRS["NS3"] == "(NXT)체결"
    assert ls.LS_STOCK_WEBSOCKET_TRS["US3"] == "(통합)체결"
    assert ls.LS_STOCK_WEBSOCKET_TRS["SC0"] == "주식주문접수"
    assert ls.LS_STOCK_WEBSOCKET_TRS["SC1"] == "주식주문체결"
    assert ls.LS_STOCK_WEBSOCKET_TRS["SC4"] == "주식주문거부"
    assert ls.LS_WEBSOCKET_CHANNELS["kospi_trade"]["tr_cd"] == "S3_"
    assert ls.LS_WEBSOCKET_CHANNELS["kosdaq_orderbook"]["tr_cd"] == "HA_"
    assert ls.LS_WEBSOCKET_CHANNELS["stock_order_accept"]["tr_type"] == "1"


def test_ls_websocket_channel_catalog_tool_is_readonly_offline() -> None:
    tool = TradingLsWebSocketChannelsTool()
    payload = json.loads(tool.execute())

    assert tool.is_readonly is True
    assert tool.repeatable is True
    assert payload["status"] == "ok"
    assert payload["broker"] == "ls"
    assert payload["network"] == "not_attempted"
    assert payload["endpoint"]["path"] == "/websocket/stock"
    assert payload["tr_count"] == 65
    assert payload["channels"]["kospi_trade"]["tr_cd"] == "S3_"
    assert payload["channels"]["kospi_trade"]["description"] == "KOSPI체결"
    assert payload["channels"]["stock_order_execution"]["tr_type"] == "1"
    assert payload["trs"]["NS3"] == "(NXT)체결"


def test_ls_websocket_url_and_subscribe_message_shape() -> None:
    cfg = _ls_cfg().with_overrides(access_token="token-ls")
    assert ls.websocket_url(cfg) == "wss://openapi.ls-sec.co.kr:29443/websocket/stock"
    assert ls.websocket_url(_ls_cfg(profile="live-readonly")) == "wss://openapi.ls-sec.co.kr:9443/websocket/stock"

    assert ls.build_websocket_subscribe_message("005930.KS", channel="kospi_trade", config=cfg) == {
        "header": {"token": "token-ls", "tr_type": "3"},
        "body": {"tr_cd": "S3_", "tr_key": "005930"},
    }
    assert ls.build_websocket_subscribe_message("035720.KQ", channel="kosdaq_orderbook", config=cfg) == {
        "header": {"token": "token-ls", "tr_type": "3"},
        "body": {"tr_cd": "HA_", "tr_key": "035720"},
    }
    assert ls.build_websocket_subscribe_message("", channel="stock_order_execution", config=cfg) == {
        "header": {"token": "token-ls", "tr_type": "1"},
        "body": {"tr_cd": "SC1", "tr_key": ""},
    }


def test_ls_websocket_parser_normalizes_trade_orderbook_and_order_events() -> None:
    trade = ls.parse_websocket_message(
        {
            "header": {"tr_cd": "S3_", "tr_key": "005930"},
            "body": {
                "shcode": "005930",
                "price": "70000",
                "change": "1000",
                "drate": "1.45",
                "cvolume": "15",
                "volume": "123456",
                "chetime": "153000",
            },
        }
    )
    orderbook = ls.parse_websocket_message(
        {
            "header": {"tr_cd": "HA_", "tr_key": "035720"},
            "body": {
                "shcode": "035720",
                "offerho1": "50000",
                "offerrem1": "10",
                "bidho1": "49950",
                "bidrem1": "8",
                "hotime": "090001",
            },
        }
    )
    order_event = ls.parse_websocket_message(
        {
            "header": {"tr_cd": "SC1"},
            "body": {
                "ordno": "86382",
                "shtnIsuno": "A005930",
                "ordqty": "2",
                "execqty": "1",
                "unercqty": "1",
                "ordprc": "60000",
                "execprc": "60000",
                "bnstp": "2",
            },
        }
    )

    assert trade["status"] == "ok"
    assert trade["channel"] == "trade"
    assert trade["symbol"] == "005930"
    assert trade["quote"]["last"] == 70000.0
    assert trade["quote"]["trade_volume"] == 15.0
    assert orderbook["status"] == "ok"
    assert orderbook["channel"] == "orderbook"
    assert orderbook["orderbook"]["asks"][0] == {"price": 50000.0, "quantity": 10.0}
    assert orderbook["orderbook"]["bids"][0] == {"price": 49950.0, "quantity": 8.0}
    assert order_event["status"] == "ok"
    assert order_event["channel"] == "order_execution"
    assert order_event["order"]["order_id"] == "86382"
    assert order_event["order"]["symbol"] == "005930"
    assert order_event["order"]["side"] == "buy"
    assert order_event["order"]["filled_quantity"] == 1.0


def test_ls_websocket_smoke_uses_token_subscribe_and_samples() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=2,
        )
    )

    assert result["status"] == "ok"
    assert result["connector"] == "ls"
    assert result["network"] == "injected_transport"
    assert result["uri"] == "wss://openapi.ls-sec.co.kr:29443/websocket/stock"
    assert result["auth"] == "access_token"
    assert result["subscription"] == {"channel": "kospi_trade", "tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"}
    assert result["received_frames"] == 2
    assert result["sample_payloads"][0]["channel"] == "trade"
    assert result["sample_payloads"][0]["symbol"] == "005930"
    assert result["sample_payloads"][1]["channel"] == "orderbook"
    assert transport.urls == ["wss://openapi.ls-sec.co.kr:29443/websocket/stock"]
    assert transport.socket.sent_json == [
        {"header": {"token": "token-ls", "tr_type": "3"}, "body": {"tr_cd": "S3_", "tr_key": "005930"}}
    ]
    assert transport.socket.closed is True
    assert client.calls[0]["path"] == "/oauth2/token"
    assert json.dumps(result["sample_payloads"], sort_keys=True)


def test_ls_websocket_smoke_records_subscription_ack_summary() -> None:
    client = _LsClient()
    transport = _SubscriptionAckLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=2,
        )
    )

    assert result["status"] == "ok"
    assert result["subscription"] == {"channel": "kospi_trade", "tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"}
    assert result["received_frames"] == 2
    assert result["subscription_events"] == [
        {
            "tr_cd": "S3_",
            "tr_type": "3",
            "status": "ok",
            "code": "00000",
            "message": "SUBSCRIBE SUCCESS",
            "tr_key_present": True,
        }
    ]
    assert len(result["sample_payloads"]) == 1
    assert result["sample_payloads"][0]["channel"] == "trade"
    assert transport.socket.closed is True


def test_ls_websocket_smoke_fails_closed_on_subscription_error_ack() -> None:
    client = _LsClient()
    transport = _SubscriptionErrorLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "subscription_error"
    assert result["received_frames"] == 1
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == [
        {
            "tr_cd": "S3_",
            "tr_type": "3",
            "status": "error",
            "code": "99999",
            "message": "SUBSCRIBE DENIED",
            "tr_key_present": True,
        }
    ]
    assert "SUBSCRIBE DENIED" in result["reason"]
    assert transport.socket.closed is True


def test_ls_websocket_smoke_fails_closed_on_malformed_frame() -> None:
    client = _LsClient()
    transport = _MalformedFrameLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "frame_error"
    assert result["received_frames"] == 1
    assert result["sample_payloads"] == []
    assert len(result["frame_errors"]) == 1
    assert result["frame_errors"][0]["status"] == "error"
    assert result["frame_errors"][0]["error"]
    assert result["frame_errors"][0]["error"] in result["reason"]
    assert "malformed-frame" not in json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert transport.socket.closed is True


def test_ls_websocket_smoke_rejects_non_positive_max_messages_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=0,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "max_messages"
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "positive integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_non_positive_message_timeout_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
            message_timeout=0,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "message_timeout"
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "positive number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_invalid_connect_attempts_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
            connect_attempts=0,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "connect_attempts"
    assert result["requested_value"] == 0
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "positive integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_invalid_reconnect_attempts_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
            reconnect_attempts=-1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "reconnect_attempts"
    assert result["requested_value"] == -1
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "non-negative integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_invalid_connect_backoff_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
            connect_backoff_seconds=-0.1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "connect_backoff_seconds"
    assert result["requested_value"] == -0.1
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "non-negative number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_invalid_reconnect_backoff_before_network() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
            reconnect_backoff_seconds=-0.1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "reconnect_backoff_seconds"
    assert result["requested_value"] == -0.1
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "non-negative number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_unknown_channel_before_token() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="unknown_channel",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "channel"
    assert result["requested_value"] == "unknown_channel"
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "supported LS WebSocket channel" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_rejects_empty_tr_key_before_token() -> None:
    client = _LsClient()
    transport = _LsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "tr_key"
    assert result["requested_value"] == ""
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert "requires a tr_key" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_ls_websocket_smoke_times_out_and_closes_socket() -> None:
    client = _LsClient()
    transport = _HangingLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=2,
            message_timeout=0.001,
        )
    )

    assert result["status"] == "timeout"
    assert result["network"] == "injected_transport"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["timeout_seconds"] == 0.001
    assert "message_timeout" in result["reason"]
    assert transport.socket.closed is True


def test_ls_websocket_smoke_retries_connect_failure_before_subscribe() -> None:
    client = _LsClient()
    transport = _FlakyLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=2,
            connect_attempts=2,
            connect_backoff_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["connection_attempts"] == 2
    assert result["received_frames"] == 2
    assert transport.urls == [
        "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
        "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
    ]
    assert len(transport.socket.sent_json) == 1
    assert transport.socket.closed is True


def test_ls_websocket_smoke_reconnects_and_resubscribes_after_receive_drop() -> None:
    client = _LsClient()
    transport = _ReconnectLsTransport()

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=2,
            reconnect_attempts=1,
            reconnect_backoff_seconds=0,
        )
    )

    first_socket, second_socket = transport.sockets
    assert result["status"] == "ok"
    assert result["reconnects"] == 1
    assert result["connection_attempts"] == 2
    assert result["received_frames"] == 2
    assert transport.urls == [
        "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
        "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
    ]
    assert len(first_socket.sent_json) == 1
    assert first_socket.sent_json == second_socket.sent_json
    assert first_socket.closed is True
    assert second_socket.closed is True


def test_ls_websocket_transport_adapter_sends_json_receives_and_closes() -> None:
    socket = _WebSocketClient()
    calls: list[str] = []

    async def connect(url):
        calls.append(url)
        return socket

    async def exercise() -> None:
        transport = ls.LsWebSocketTransport(connect_factory=connect)
        active = await transport.connect("wss://openapi.ls-sec.co.kr:29443/websocket/stock")
        await active.send_json({"header": {"token": "token-ls", "tr_type": "3"}, "body": {"tr_cd": "S3_", "tr_key": "005930"}})
        assert await active.receive() == json.dumps(
            {"header": {"tr_cd": "S3_", "tr_key": "005930"}, "body": {"shcode": "005930", "price": "70000"}}
        )
        await active.close()

    asyncio.run(exercise())

    assert calls == ["wss://openapi.ls-sec.co.kr:29443/websocket/stock"]
    assert json.loads(socket.sent[0]) == {
        "header": {"token": "token-ls", "tr_type": "3"},
        "body": {"tr_cd": "S3_", "tr_key": "005930"},
    }
    assert socket.closed is True


def test_ls_websocket_smoke_uses_default_transport_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _LsClient()
    transport = _LsTransport()
    calls: list[str] = []

    def factory():
        calls.append("factory")
        return transport

    monkeypatch.setattr(ls, "create_websocket_transport", factory)

    result = asyncio.run(
        ls.run_websocket_smoke(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            client=client,
            max_messages=2,
        )
    )

    assert result["status"] == "ok"
    assert result["network"] == "websocket_transport"
    assert calls == ["factory"]
    assert transport.urls == ["wss://openapi.ls-sec.co.kr:29443/websocket/stock"]
    assert client.calls[0]["path"] == "/oauth2/token"


def test_ls_websocket_smoke_reports_missing_websockets_when_default_transport_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def factory():
        raise KoreanConnectorConfigError("LS WebSocket transport requires the websockets package.")

    monkeypatch.setattr(ls, "create_websocket_transport", factory, raising=False)

    result = asyncio.run(ls.run_websocket_smoke(_ls_cfg(), channel="kospi_trade", tr_key="005930.KS"))

    assert result["status"] == "not_configured"
    assert result["connector"] == "ls"
    assert result["missing"] == ["websockets"]
    assert result["network"] == "not_attempted"
    assert "websockets package" in result["error"]


def test_ls_websocket_smoke_evidence_redacts_subscription_and_raw_samples() -> None:
    smoke_result = {
        "status": "ok",
        "connector": "ls",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
        "auth": "access_token",
        "subscription": {"channel": "kospi_trade", "tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"},
        "received_frames": 2,
        "sample_payloads": [
            {
                "status": "ok",
                "channel": "trade",
                "tr_cd": "S3_",
                "symbol": "005930",
                "quote": {
                    "last": 70000.0,
                    "change": 1000.0,
                    "change_rate": 1.45,
                    "trade_volume": 15.0,
                    "volume": 123456.0,
                    "time": "153000",
                    "raw": {"shcode": "005930", "price": "70000", "volume": "123456"},
                },
                "raw": {"header": {"token": "token-ls", "tr_key": "005930"}, "body": {"shcode": "005930"}},
            },
            {
                "status": "ok",
                "channel": "orderbook",
                "tr_cd": "HA_",
                "symbol": "035720",
                "orderbook": {
                    "asks": [{"price": 50000.0, "quantity": 10.0}],
                    "bids": [{"price": 49950.0, "quantity": 8.0}],
                    "raw": {"shcode": "035720", "offerho1": "50000"},
                },
                "raw": {"body": {"shcode": "035720"}},
            },
        ],
    }

    evidence = ls.websocket_smoke_evidence(smoke_result, max_samples=1)

    assert evidence["status"] == "ok"
    assert evidence["connector"] == "ls"
    assert evidence["subscription"] == {
        "channel": "kospi_trade",
        "tr_cd": "S3_",
        "tr_type": "3",
        "tr_key_present": True,
        "tr_key_kind": "symbol",
    }
    assert evidence["sample_count"] == 2
    assert evidence["sample_payloads"] == [
        {
            "status": "ok",
            "channel": "trade",
            "tr_cd": "S3_",
            "symbol_present": True,
            "quote_keys": ["change", "change_rate", "last", "time", "trade_volume", "volume"],
            "raw_header_keys": ["token", "tr_key"],
            "raw_body_keys": ["shcode"],
        }
    ]
    dumped = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "005930" not in dumped
    assert "035720" not in dumped
    assert "token-ls" not in dumped
    assert "70000" not in dumped


def test_ls_websocket_smoke_evidence_redacts_subscription_ack_values() -> None:
    smoke_result = {
        "status": "ok",
        "connector": "ls",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
        "auth": "access_token",
        "subscription": {"channel": "kospi_trade", "tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"},
        "subscription_events": [
            {
                "tr_cd": "S3_",
                "tr_type": "3",
                "status": "ok",
                "code": "00000",
                "message": "SUBSCRIBE SUCCESS",
                "tr_key": "005930",
                "token": "token-ls",
                "tr_key_present": True,
            }
        ],
        "received_frames": 1,
        "sample_payloads": [],
    }

    evidence = ls.websocket_smoke_evidence(smoke_result)

    assert evidence["subscription_events"] == [
        {
            "tr_cd": "S3_",
            "tr_type": "3",
            "status": "ok",
            "code": "00000",
            "message": "SUBSCRIBE SUCCESS",
            "tr_key_present": True,
        }
    ]
    dumped = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "005930" not in dumped
    assert "token-ls" not in dumped


def test_ls_websocket_smoke_with_evidence_writes_subscription_error_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _SubscriptionErrorLsTransport()
    target = tmp_path / "subscription-error" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "subscription_error"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "subscription_error"
    assert payload["subscription_events"][0]["message"] == "SUBSCRIBE DENIED"
    assert "SUBSCRIBE DENIED" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert "token-ls" not in serialized


def test_ls_websocket_smoke_with_evidence_writes_frame_error_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _MalformedFrameLsTransport()
    target = tmp_path / "frame-error" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "frame_error"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "frame_error"
    assert len(payload["frame_errors"]) == 1
    assert payload["frame_errors"][0]["status"] == "error"
    assert payload["frame_errors"][0]["error"]
    assert payload["frame_errors"][0]["error"] in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "malformed-frame" not in serialized
    assert "005930" not in serialized


def test_ls_websocket_smoke_with_evidence_writes_invalid_max_messages_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-max-messages" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "max_messages"
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "positive integer" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_invalid_message_timeout_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-message-timeout" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
            message_timeout=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "message_timeout"
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "positive number" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_invalid_connect_attempts_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-connect-attempts" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
            connect_attempts=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "connect_attempts"
    assert payload["requested_value"] == 0
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "positive integer" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_invalid_reconnect_attempts_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-reconnect-attempts" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
            reconnect_attempts=-1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "reconnect_attempts"
    assert payload["requested_value"] == -1
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "non-negative integer" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_invalid_connect_backoff_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-connect-backoff" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
            connect_backoff_seconds=-0.1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "connect_backoff_seconds"
    assert payload["requested_value"] == -0.1
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "non-negative number" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_invalid_reconnect_backoff_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-reconnect-backoff" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
            reconnect_backoff_seconds=-0.1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "reconnect_backoff_seconds"
    assert payload["requested_value"] == -0.1
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "non-negative number" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_unknown_channel_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-channel" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="unknown_channel",
            tr_key="005930.KS",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "channel"
    assert payload["requested_value"] == "unknown_channel"
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "supported LS WebSocket channel" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_empty_tr_key_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "invalid-tr-key" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["parameter"] == "tr_key"
    assert payload["requested_value"] == ""
    assert payload["network"] == "not_attempted"
    assert payload["received_frames"] == 0
    assert "requires a tr_key" in payload["reason"]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_ls_write_websocket_smoke_evidence_saves_redacted_json(tmp_path) -> None:
    result = {
        "status": "ok",
        "connector": "ls",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "wss://openapi.ls-sec.co.kr:29443/websocket/stock",
        "auth": "access_token",
        "subscription": {"channel": "kospi_trade", "tr_cd": "S3_", "tr_type": "3", "tr_key": "005930"},
        "received_frames": 1,
        "sample_payloads": [
            {
                "status": "ok",
                "channel": "trade",
                "tr_cd": "S3_",
                "symbol": "005930",
                "quote": {
                    "last": 70000.0,
                    "raw": {"shcode": "005930", "price": "70000", "volume": "123456"},
                },
                "raw": {"header": {"token": "token-ls", "tr_key": "005930"}, "body": {"shcode": "005930"}},
            }
        ],
    }
    target = tmp_path / "nested" / "ls-websocket-smoke.json"

    written = ls.write_websocket_smoke_evidence(result, target)

    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["subscription"] == {
        "channel": "kospi_trade",
        "tr_cd": "S3_",
        "tr_type": "3",
        "tr_key_present": True,
        "tr_key_kind": "symbol",
    }
    assert payload["sample_payloads"][0]["symbol_present"] is True
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert "token-ls" not in serialized
    assert "70000" not in serialized
    assert "raw_values" not in serialized


def test_ls_websocket_smoke_with_evidence_requires_broker_opt_in(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
        )
    )

    assert result["status"] == "not_run"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert "allow_broker_calls=True" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert not target.exists()


def test_ls_websocket_smoke_with_evidence_blocks_live_without_opt_in(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "ls-websocket-smoke-live.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(profile="live"),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
        )
    )

    assert result["status"] == "blocked"
    assert result["environment"] == "live"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert "allow_live=True" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert not target.exists()


def test_ls_websocket_smoke_with_evidence_rejects_directory_path_before_broker_call(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "ls-websocket-smoke-dir"
    target.mkdir()

    try:
        result = asyncio.run(
            ls.run_websocket_smoke_with_evidence(
                _ls_cfg(),
                channel="kospi_trade",
                tr_key="005930",
                evidence_path=target,
                client=client,
                transport=transport,
                allow_broker_calls=True,
            )
        )
    except IsADirectoryError:
        result = {"status": "raised", "network": "broker_called"}

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert result["parameter"] == "evidence_path"
    assert str(target) in result["requested_value"]
    assert "file path" in result["reason"]
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_rejects_file_parent_before_broker_call(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    parent = tmp_path / "not-a-directory"
    parent.write_text("existing file", encoding="utf-8")
    target = parent / "ls-websocket-smoke.json"

    try:
        result = asyncio.run(
            ls.run_websocket_smoke_with_evidence(
                _ls_cfg(),
                channel="kospi_trade",
                tr_key="005930",
                evidence_path=target,
                client=client,
                transport=transport,
                allow_broker_calls=True,
            )
        )
    except (FileExistsError, NotADirectoryError):
        result = {"status": "raised", "network": "broker_called"}

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert result["parameter"] == "evidence_path"
    assert str(target) in result["requested_value"]
    assert "parent directory" in result["reason"]
    assert client.calls == []
    assert transport.urls == []


def test_ls_websocket_smoke_with_evidence_writes_redacted_json_when_allowed(tmp_path) -> None:
    client = _LsClient()
    transport = _LsTransport()
    target = tmp_path / "nested" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=2,
        )
    )

    assert result["status"] == "ok"
    assert result["evidence_path"] == str(target)
    assert result["subscription"] == {
        "channel": "kospi_trade",
        "tr_cd": "S3_",
        "tr_type": "3",
        "tr_key_present": True,
        "tr_key_kind": "symbol",
    }
    assert result["sample_count"] == 2
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {key: value for key, value in result.items() if key != "evidence_path"}
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert "005930" not in serialized
    assert "035720" not in serialized
    assert "token-ls" not in serialized
    assert "app-secret" not in serialized
    assert "70000" not in serialized


def test_ls_websocket_smoke_with_evidence_writes_timeout_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _HangingLsTransport()
    target = tmp_path / "timeout" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=2,
            message_timeout=0.001,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "timeout"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "timeout"
    assert payload["timeout_seconds"] == 0.001
    assert "message_timeout" in payload["reason"]
    assert "005930" not in json.dumps(payload, sort_keys=True)


def test_ls_websocket_smoke_with_evidence_writes_connection_error_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _FailingLsTransport()
    target = tmp_path / "connection-error" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=2,
            connect_attempts=2,
            connect_backoff_seconds=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "connection_error"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "connection_error"
    assert payload["connection_attempts"] == 2
    assert "temporary connect failure" in payload["reason"]
    assert "005930" not in json.dumps(payload, sort_keys=True)


def test_ls_websocket_smoke_with_evidence_writes_reconnect_summary(tmp_path) -> None:
    client = _LsClient()
    transport = _ReconnectLsTransport()
    target = tmp_path / "reconnect" / "ls-websocket-smoke.json"

    result = asyncio.run(
        ls.run_websocket_smoke_with_evidence(
            _ls_cfg(),
            channel="kospi_trade",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=2,
            reconnect_attempts=1,
            reconnect_backoff_seconds=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert result["reconnects"] == 1
    assert result["connection_attempts"] == 2
    assert payload["status"] == "ok"
    assert payload["reconnects"] == 1
    assert payload["connection_attempts"] == 2
    assert payload["subscription"]["tr_key_present"] is True
    assert "tr_key" not in payload["subscription"]


def test_ls_quote_requests_token_and_official_t1101_contract() -> None:
    client = _LsClient()
    out = ls.get_quote("078020.KS", config=_ls_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "078020"
    assert out["quote"]["last"] == 4545.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/token"
    assert token_call["params"] == {"grant_type": "client_credentials", "appkey": "app-key", "appsecretkey": "app-secret", "scope": "oob"}
    assert token_call["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert quote_call["path"] == "/stock/market-data"
    assert quote_call["headers"]["authorization"] == "Bearer token-ls"
    assert quote_call["headers"]["tr_cd"] == "t1101"
    assert quote_call["headers"]["tr_cont"] == "N"
    assert quote_call["headers"]["tr_cont_key"] == ""
    assert quote_call["json"] == {"t1101InBlock": {"shcode": "078020"}}


def test_ls_account_snapshot_uses_official_t0424_contract() -> None:
    client = _LsClient()
    out = ls.get_account_snapshot(_ls_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["account"]["cash"] == 203287854.0
    assert out["positions"][0]["symbol"] == "249420"
    assert out["positions"][0]["quantity"] == 1091.0

    balance_call = client.calls[-1]
    assert balance_call["path"] == "/stock/accno"
    assert balance_call["headers"]["tr_cd"] == "t0424"
    assert balance_call["json"] == {
        "t0424InBlock": {"prcgb": "", "chegb": "", "dangb": "", "charge": "", "cts_expcode": ""}
    }


def test_ls_order_and_cancel_use_official_stock_order_contracts() -> None:
    client = _LsClient()
    order = ls.place_order(
        _ls_cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
        exchange="KRX",
    )
    cancel = ls.cancel_order(_ls_cfg(), "32004", symbol="005930", quantity=3, client=client)
    assert order["status"] == "ok"
    assert order["order_id"] == "32004"
    assert cancel["status"] == "ok"

    order_call = next(call for call in client.calls if call["headers"].get("tr_cd") == "CSPAT00601")
    cancel_call = next(call for call in client.calls if call["headers"].get("tr_cd") == "CSPAT00801")
    assert order_call["path"] == "/stock/order"
    assert order_call["json"] == {
        "CSPAT00601InBlock1": {
            "IsuNo": "A005930",
            "OrdQty": 3,
            "OrdPrc": 70000,
            "BnsTpCode": "2",
            "OrdprcPtnCode": "00",
            "MgntrnCode": "000",
            "LoanDt": "",
            "OrdCndiTpCode": "0",
            "MbrNo": "KRX",
        }
    }
    assert cancel_call["json"] == {"CSPAT00801InBlock1": {"OrgOrdNo": 32004, "IsuNo": "A005930", "OrdQty": 3}}


def test_ls_modify_order_uses_official_cspat00701_contract() -> None:
    client = _LsClient()
    out = ls.modify_order(_ls_cfg(), "32004", symbol="005930", quantity=2, limit_price=71000, client=client)
    assert out["status"] == "ok"
    assert out["order_id"] == "32004"

    modify_call = next(call for call in client.calls if call["headers"].get("tr_cd") == "CSPAT00701")
    assert modify_call["path"] == "/stock/order"
    assert modify_call["json"] == {
        "CSPAT00701InBlock1": {
            "OrgOrdNo": 32004,
            "IsuNo": "A005930",
            "OrdQty": 2,
            "OrdprcPtnCode": "00",
            "OrdCndiTpCode": "0",
            "OrdPrc": 71000,
        }
    }


def test_kiwoom_catalog_matches_official_openapi_guides() -> None:
    assert kiwoom.KIWOOM_REST_ENDPOINTS["auth_token"]["path"] == "/oauth2/token"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_info"]["path"] == "/api/dostk/stkinfo"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_info"]["api_id"] == "ka10001"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["daily_chart"]["path"] == "/api/dostk/chart"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["daily_chart"]["api_id"] == "ka10081"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["account_balance"]["api_id"] == "kt00018"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["open_orders"]["api_id"] == "ka10075"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_buy_order"]["api_id"] == "kt10000"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_sell_order"]["api_id"] == "kt10001"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_cancel_order"]["api_id"] == "kt10003"


def test_kiwoom_quote_requests_token_and_official_ka10001_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.get_quote("KRX:005930", config=_kiwoom_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "005930"
    assert out["quote"]["last"] == 70000.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/token"
    assert token_call["json"] == {"grant_type": "client_credentials", "appkey": "app-key", "secretkey": "app-secret"}
    assert quote_call["path"] == "/api/dostk/stkinfo"
    assert quote_call["headers"]["authorization"] == "Bearer token-kw"
    assert quote_call["headers"]["api-id"] == "ka10001"
    assert quote_call["json"] == {"stk_cd": "005930"}


def test_kiwoom_history_uses_official_ka10081_daily_chart_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.get_historical_bars("005930.KS", config=_kiwoom_cfg(), client=client, limit=1, base_date="20260604")
    assert out["status"] == "ok"
    assert out["bars"][0]["date"] == "20260604"
    assert out["bars"][0]["close"] == 70000.0

    history_call = client.calls[-1]
    assert history_call["path"] == "/api/dostk/chart"
    assert history_call["headers"]["api-id"] == "ka10081"
    assert history_call["json"] == {"stk_cd": "005930", "base_dt": "20260604", "upd_stkpc_tp": "1"}


def test_kiwoom_account_and_open_orders_use_official_account_contracts() -> None:
    client = _KiwoomClient()
    snapshot = kiwoom.get_account_snapshot(_kiwoom_cfg(), client=client)
    orders = kiwoom.get_open_orders(_kiwoom_cfg(), client=client)
    assert snapshot["status"] == "ok"
    assert snapshot["account"]["total_value"] == 640000.0
    assert snapshot["positions"][0]["symbol"] == "005930"
    assert orders["status"] == "ok"
    assert orders["orders"][0]["order_id"] == "1234567"

    balance_call = _kiwoom_call(client, "kt00018")
    open_orders_call = _kiwoom_call(client, "ka10075")
    assert balance_call["path"] == "/api/dostk/acnt"
    assert balance_call["headers"]["api-id"] == "kt00018"
    assert balance_call["json"] == {"qry_tp": "1", "dmst_stex_tp": "KRX"}
    assert open_orders_call["headers"]["api-id"] == "ka10075"
    assert open_orders_call["json"] == {"all_stk_tp": "0", "trde_tp": "0", "stk_cd": ""}


def test_kiwoom_order_and_cancel_use_official_order_api_ids() -> None:
    client = _KiwoomClient()
    buy = kiwoom.place_order(
        _kiwoom_cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
        exchange="KRX",
    )
    sell = kiwoom.place_order(
        _kiwoom_cfg(),
        symbol="005930",
        side="sell",
        quantity=1,
        order_type="market",
        client=client,
        exchange="KRX",
    )
    cancel = kiwoom.cancel_order(_kiwoom_cfg(), "7654321", symbol="005930", quantity=0, client=client, exchange="KRX")
    assert buy["status"] == "ok"
    assert sell["status"] == "ok"
    assert cancel["status"] == "ok"

    buy_call = _kiwoom_call(client, "kt10000")
    sell_call = _kiwoom_call(client, "kt10001")
    cancel_call = _kiwoom_call(client, "kt10003")
    assert buy_call["path"] == "/api/dostk/ordr"
    assert buy_call["headers"]["api-id"] == "kt10000"
    assert buy_call["json"] == {"dmst_stex_tp": "KRX", "stk_cd": "005930", "ord_qty": "3", "ord_uv": "70000", "trde_tp": "0"}
    assert sell_call["headers"]["api-id"] == "kt10001"
    assert sell_call["json"]["trde_tp"] == "3"
    assert sell_call["json"]["ord_uv"] == ""
    assert cancel_call["headers"]["api-id"] == "kt10003"
    assert cancel_call["json"] == {"dmst_stex_tp": "KRX", "orig_ord_no": "7654321", "stk_cd": "005930", "cncl_qty": "0"}


def test_kiwoom_modify_order_uses_official_kt10002_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.modify_order(_kiwoom_cfg(), "7654321", symbol="005930", quantity=2, limit_price=71000, client=client, exchange="KRX")
    assert out["status"] == "ok"
    assert out["order_id"] == "7654321"

    modify_call = _kiwoom_call(client, "kt10002")
    assert modify_call["path"] == "/api/dostk/ordr"
    assert modify_call["json"] == {
        "dmst_stex_tp": "KRX",
        "orig_ord_no": "7654321",
        "stk_cd": "005930",
        "mdfy_qty": "2",
        "mdfy_uv": "71000",
        "mdfy_cond_uv": "",
    }
