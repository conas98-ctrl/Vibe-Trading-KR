"""KIS official REST contract tests.

These tests lock the endpoint paths and TR IDs against the official
open-trading-api sample surface without requiring live KIS credentials.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

import pytest

from src.trading.connectors.kis import sdk as kis
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


class _KisClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "json": json, "headers": headers or {}})
        if path == "/oauth2/tokenP":
            return _Response({"access_token": "token-123", "access_token_token_expired": "29991231235959"})
        if path == "/oauth2/Approval":
            return _Response({"approval_key": "approval-123"})
        if path == "/uapi/hashkey":
            return _Response({"HASH": "hash-123"})
        if path == "/uapi/domestic-stock/v1/trading/order-cash":
            return _Response({"rt_cd": "0", "output": {"ODNO": "00001", "KRX_FWDG_ORD_ORGNO": "91234"}})
        if path == "/uapi/domestic-stock/v1/trading/order-rvsecncl":
            return _Response({"rt_cd": "0", "output": {"ODNO": "00001", "KRX_FWDG_ORD_ORGNO": "91234"}})
        raise AssertionError(f"unexpected POST {path}")

    def get(self, url, *, params=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "GET", "path": path, "params": params or {}, "headers": headers or {}})
        if path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return _Response(
                {
                    "rt_cd": "0",
                    "output": {
                        "stck_prpr": "70000",
                        "prdy_vrss": "1000",
                        "prdy_ctrt": "1.45",
                        "acml_vol": "123456",
                        "acml_tr_pbmn": "8900000000",
                    },
                }
            )
        if path == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice":
            return _Response(
                {
                    "rt_cd": "0",
                    "output1": {"stck_shrn_iscd": "005930"},
                    "output2": [
                        {
                            "stck_bsop_date": "20260604",
                            "stck_oprc": "69000",
                            "stck_hgpr": "71000",
                            "stck_lwpr": "68000",
                            "stck_clpr": "70000",
                            "acml_vol": "1000",
                        }
                    ],
                }
            )
        if path == "/uapi/domestic-stock/v1/trading/inquire-balance":
            return _Response(
                {
                    "rt_cd": "0",
                    "output1": [{"pdno": "005930", "hldg_qty": "2", "evlu_amt": "140000"}],
                    "output2": [{"dnca_tot_amt": "500000", "tot_evlu_amt": "640000"}],
                },
                headers={"tr_cont": ""},
            )
        if path == "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl":
            return _Response(
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": "00001",
                            "ord_gno_brno": "91234",
                            "pdno": "005930",
                            "ord_qty": "5",
                            "tot_ccld_qty": "2",
                            "psbl_qty": "3",
                            "sll_buy_dvsn_cd": "02",
                            "ord_unpr": "70000",
                        }
                    ],
                    "ctx_area_fk100": "",
                    "ctx_area_nk100": "",
                },
                headers={"tr_cont": ""},
            )
        raise AssertionError(f"unexpected GET {path}")


class _ApprovalFailureKisClient(_KisClient):
    def post(self, url, *, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "json": json, "headers": headers or {}})
        if path == "/oauth2/Approval":
            raise RuntimeError("approval service unavailable")
        raise AssertionError(f"unexpected POST {path}")


class _KisSocket:
    def __init__(self):
        self.sent_json: list[dict] = []
        self.pongs: list[str | bytes] = []
        self.closed = False
        self.messages: list[str | bytes] = [
            '{"header":{"tr_id":"H0STCNT0","tr_key":"005930","encrypt":"N"},"body":{"rt_cd":"0","msg1":"SUBSCRIBE SUCCESS"}}',
            b'{"header":{"tr_id":"PINGPONG"}}',
            "0|H0STCNT0|001|005930^153000^70000^2^1000^1.45^69500^69000^71000^68000^70100^70000^15",
        ]

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def receive(self):
        return self.messages.pop(0)

    async def pong(self, payload):
        self.pongs.append(payload)

    async def close(self):
        self.closed = True


class _KisTransport:
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _KisSocket()

    async def connect(self, url):
        self.urls.append(url)
        return self.socket


class _NoticeAckKisSocket(_KisSocket):
    def __init__(self):
        super().__init__()
        self.messages = [
            (
                '{"header":{"tr_id":"H0STCNI9","tr_key":"MYHTSID","encrypt":"Y"},'
                '"body":{"rt_cd":"0","msg1":"SUBSCRIBE SUCCESS","output":{"iv":"iv-123","key":"key-123"}}}'
            )
        ]


class _NoticeAckKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _NoticeAckKisSocket()


class _NoticeErrorKisSocket(_KisSocket):
    def __init__(self):
        super().__init__()
        self.messages = [
            (
                '{"header":{"tr_id":"H0STCNI9","tr_key":"MYHTSID","encrypt":"N"},'
                '"body":{"rt_cd":"1","msg1":"SUBSCRIBE DENIED","output":{"iv":"iv-denied","key":"key-denied"}}}'
            )
        ]


class _NoticeErrorKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _NoticeErrorKisSocket()


class _MalformedFrameKisSocket(_KisSocket):
    def __init__(self):
        super().__init__()
        self.messages = ["malformed-frame"]


class _MalformedFrameKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _MalformedFrameKisSocket()


class _HangingKisSocket(_KisSocket):
    async def receive(self):
        await asyncio.sleep(1)


class _HangingKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _HangingKisSocket()


class _FlakyKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _KisSocket()
        self.failures_remaining = 1

    async def connect(self, url):
        self.urls.append(url)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise OSError("temporary connect failure")
        return self.socket


class _FailingKisTransport(_KisTransport):
    def __init__(self):
        self.urls: list[str] = []
        self.socket = _KisSocket()

    async def connect(self, url):
        self.urls.append(url)
        raise OSError("temporary connect failure")


class _DisconnectingKisSocket(_KisSocket):
    async def receive(self):
        raise ConnectionError("socket dropped after subscribe")


class _ReconnectKisTransport:
    def __init__(self):
        self.urls: list[str] = []
        self.sockets: list[_KisSocket] = [_DisconnectingKisSocket(), _KisSocket()]
        self._index = 0

    async def connect(self, url):
        self.urls.append(url)
        socket = self.sockets[self._index]
        self._index += 1
        return socket


class _WebSocketClient:
    def __init__(self):
        self.sent: list[str] = []
        self.pongs: list[str | bytes] = []
        self.closed = False
        self.messages: list[str | bytes] = [
            b'{"header":{"tr_id":"PINGPONG"}}',
            "0|H0STCNT0|001|005930^153000^70000",
        ]

    async def send(self, payload):
        self.sent.append(payload)

    async def recv(self):
        return self.messages.pop(0)

    async def pong(self, payload):
        self.pongs.append(payload)

    async def close(self):
        self.closed = True


def _cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(
        connector="kis",
        profile=profile,
        app_key="app-key",
        app_secret="app-secret",
        account="12345678",
        account_product_code="01",
        paper_url=kis.PAPER_URL,
        live_url=kis.LIVE_URL,
    )


def test_kis_catalog_matches_official_domestic_stock_samples() -> None:
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["websocket_approval"]["path"] == "/oauth2/Approval"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_price"]["path"] == (
        "/uapi/domestic-stock/v1/quotations/inquire-price"
    )
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_price"]["tr_id"] == "FHKST01010100"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_daily_itemchartprice"]["tr_id"] == "FHKST03010100"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_balance"]["paper_tr_id"] == "VTTC8434R"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_psbl_rvsecncl"]["path"] == (
        "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    )
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_psbl_rvsecncl"]["tr_id"] == "TTTC0084R"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["order_cash"]["paper_buy_tr_id"] == "VTTC0012U"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["order_cash"]["live_sell_tr_id"] == "TTTC0011U"


def test_kis_websocket_catalog_matches_official_domestic_stock_samples() -> None:
    assert kis.KIS_WEBSOCKET_URLS == {
        "paper": "ws://ops.koreainvestment.com:31000",
        "live": "ws://ops.koreainvestment.com:21000",
    }
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_krx"]["tr_id"] == "H0STASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_nxt"]["tr_id"] == "H0NXASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_total"]["tr_id"] == "H0UNASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_krx"]["tr_id"] == "H0STCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_nxt"]["tr_id"] == "H0NXCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_total"]["tr_id"] == "H0UNCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_notice"]["live_tr_id"] == "H0STCNI0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_notice"]["paper_tr_id"] == "H0STCNI9"
    assert kis.KIS_WEBSOCKET_CHANNELS["program_trade_total"]["tr_id"] == "H0UNPGM0"


def test_kis_websocket_approval_posts_official_approval_contract() -> None:
    client = _KisClient()
    approval_key = kis.issue_websocket_approval_key(_cfg(), client=client)
    assert approval_key == "approval-123"

    call = client.calls[-1]
    assert call["path"] == "/oauth2/Approval"
    assert call["json"] == {
        "grant_type": "client_credentials",
        "appkey": "app-key",
        "secretkey": "app-secret",
    }
    assert call["headers"]["Content-Type"] == "application/json"


def test_kis_websocket_url_and_subscribe_message_shape() -> None:
    assert kis.websocket_url(_cfg()) == "ws://ops.koreainvestment.com:31000"
    assert kis.websocket_url(_cfg(profile="live")) == "ws://ops.koreainvestment.com:21000"

    msg = kis.build_websocket_subscribe_message(
        "005930.KS",
        channel="ccnl_krx",
        approval_key="approval-123",
        config=_cfg(),
    )
    assert msg == {
        "header": {
            "content-type": "utf-8",
            "approval_key": "approval-123",
            "tr_type": "1",
            "custtype": "P",
        },
        "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}},
    }

    notice = kis.build_websocket_subscribe_message(
        "MYHTSID",
        channel="ccnl_notice",
        approval_key="approval-123",
        config=_cfg(),
    )
    assert notice["body"]["input"] == {"tr_id": "H0STCNI9", "tr_key": "MYHTSID"}

    live_notice = kis.build_websocket_subscribe_message(
        "MYHTSID",
        channel="ccnl_notice",
        approval_key="approval-123",
        config=_cfg(profile="live"),
    )
    assert live_notice["body"]["input"]["tr_id"] == "H0STCNI0"


def test_kis_parse_websocket_trade_and_system_frames() -> None:
    trade = kis.parse_websocket_message(
        "0|H0STCNT0|001|005930^153000^70000^2^1000^1.45^69500^69000^71000^68000^70100^70000^15",
        channel="ccnl_krx",
    )
    assert trade["type"] == "data"
    assert trade["tr_id"] == "H0STCNT0"
    assert trade["fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert trade["event"]["symbol"] == "005930"
    assert trade["event"]["last"] == 70000.0
    assert trade["event"]["trade_volume"] == 15.0

    system = kis.parse_websocket_message(
        (
            '{"header":{"tr_id":"H0STCNI9","tr_key":"MYHTSID","encrypt":"Y"},'
            '"body":{"rt_cd":"0","msg1":"SUBSCRIBE SUCCESS","output":{"iv":"iv-123","key":"key-123"}}}'
        )
    )
    assert system["type"] == "system"
    assert system["status"] == "ok"
    assert system["tr_id"] == "H0STCNI9"
    assert system["encrypted"] is True
    assert system["iv"] == "iv-123"
    assert system["key"] == "key-123"

    pingpong = b'{"header":{"tr_id":"PINGPONG"}}'
    pingpong_event = kis.parse_websocket_message(pingpong)
    assert pingpong_event["type"] == "system"
    assert pingpong_event["is_pingpong"] is True
    assert kis.websocket_pingpong_payload(pingpong) == pingpong
    assert kis.websocket_pingpong_payload(system) is None


def _kis_trade_values(
    *,
    symbol: str = "005930",
    time: str = "123929",
    price: str = "73100",
    trade_volume: str = "42",
    cumulative_volume: str = "1000",
    execution_side: str = "1",
) -> list[str]:
    values = [
        symbol,
        time,
        price,
        "2",
        "500",
        "0.69",
        "72050",
        "72000",
        "73500",
        "71000",
        "73100",
        "73000",
        trade_volume,
        cumulative_volume,
        "73000000",
        "12",
        "18",
        "6",
        "130.5",
        "600",
        "900",
        execution_side,
        "60.0",
        "110.5",
        "090000",
        "2",
        "1100",
        "123000",
        "2",
        "500",
        "091000",
        "2",
        "1000",
        "20260605",
        "20",
        "N",
        "300",
        "250",
        "3000",
        "2500",
        "5.5",
        "900",
        "111.1",
        "0",
        "0",
        "72000",
    ]
    assert len(values) == len(kis.KIS_WEBSOCKET_TRADE_FIELDS)
    return values


def test_kis_websocket_trade_parser_handles_official_multi_record_frame() -> None:
    first = _kis_trade_values()
    second = _kis_trade_values(
        symbol="000660",
        time="123930",
        price="121000",
        trade_volume="7",
        cumulative_volume="2000",
        execution_side="5",
    )

    ticks = kis.parse_websocket_trade_ticks(f"0|H0STCNT0|002|{'^'.join(first + second)}")

    assert [tick["symbol"] for tick in ticks] == ["005930", "000660"]
    assert ticks[0]["time"] == "123929"
    assert ticks[0]["last"] == 73100.0
    assert ticks[0]["trade_volume"] == 42.0
    assert ticks[0]["signed_trade_volume"] == 42.0
    assert ticks[0]["cumulative_volume"] == 1000.0
    assert ticks[0]["cumulative_trade_value"] == 73000000.0
    assert ticks[0]["ask"] == 73100.0
    assert ticks[0]["bid"] == 73000.0
    assert ticks[0]["trade_strength"] == 130.5
    assert ticks[0]["business_date"] == "20260605"
    assert ticks[0]["trading_halt"] is False
    assert ticks[0]["raw_fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert ticks[0]["raw_values"] == first
    assert ticks[1]["trade_volume"] == 7.0
    assert ticks[1]["signed_trade_volume"] == -7.0


def test_kis_websocket_trade_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected H0STCNT0"):
        kis.parse_websocket_trade_ticks("0|H0STASP0|001|005930")

    truncated = "^".join(_kis_trade_values()[:-1])
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 46 values per H0STCNT0 tick"):
        kis.parse_websocket_trade_ticks(f"0|H0STCNT0|001|{truncated}")


def _kis_orderbook_values(
    *,
    symbol: str = "005930",
    time: str = "123930",
    ask1: str = "73100",
    bid1: str = "73000",
    total_ask: str = "3000",
    total_bid: str = "2500",
) -> list[str]:
    asks = [str(int(ask1) + (level - 1) * 100) for level in range(1, 11)]
    bids = [str(int(bid1) - (level - 1) * 100) for level in range(1, 11)]
    ask_quantities = [str(100 * level) for level in range(1, 11)]
    bid_quantities = [str(90 * level) for level in range(1, 11)]
    values = [
        symbol,
        time,
        "0",
        *asks,
        *bids,
        *ask_quantities,
        *bid_quantities,
        total_ask,
        total_bid,
        "120",
        "90",
        "73100",
        "10",
        "500",
        "100",
        "2",
        "0.14",
        "12345",
        "5",
        "-3",
        "2",
        "-1",
        "00",
    ]
    assert len(values) == len(kis.KIS_WEBSOCKET_ORDERBOOK_FIELDS)
    return values


def test_kis_websocket_orderbook_parser_handles_official_multi_record_frame() -> None:
    first = _kis_orderbook_values()
    second = _kis_orderbook_values(
        symbol="000660",
        time="123931",
        ask1="121100",
        bid1="121000",
        total_ask="7000",
        total_bid="6500",
    )

    books = kis.parse_websocket_orderbooks(f"0|H0STASP0|002|{'^'.join(first + second)}")

    assert [book["symbol"] for book in books] == ["005930", "000660"]
    assert books[0]["time"] == "123930"
    assert books[0]["asks"][0] == {"level": 1, "price": 73100.0, "quantity": 100.0}
    assert books[0]["asks"][-1] == {"level": 10, "price": 74000.0, "quantity": 1000.0}
    assert books[0]["bids"][0] == {"level": 1, "price": 73000.0, "quantity": 90.0}
    assert books[0]["bids"][-1] == {"level": 10, "price": 72100.0, "quantity": 900.0}
    assert books[0]["total_ask_quantity"] == 3000.0
    assert books[0]["total_bid_quantity"] == 2500.0
    assert books[0]["overtime_total_ask_quantity"] == 120.0
    assert books[0]["anticipated_price"] == 73100.0
    assert books[0]["cumulative_volume"] == 12345.0
    assert books[0]["stock_deal_class_code"] == "00"
    assert books[0]["raw_fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert books[0]["raw_values"] == first
    assert books[1]["asks"][0]["price"] == 121100.0
    assert books[1]["total_bid_quantity"] == 6500.0


def test_kis_websocket_orderbook_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected H0STASP0"):
        kis.parse_websocket_orderbooks("0|H0STCNT0|001|005930")

    truncated = "^".join(_kis_orderbook_values()[:-1])
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 59 values per H0STASP0 book"):
        kis.parse_websocket_orderbooks(f"0|H0STASP0|001|{truncated}")


def test_kis_websocket_smoke_uses_approval_subscribe_pingpong_and_samples() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930.KS",
            client=client,
            transport=transport,
            max_messages=3,
        )
    )

    assert result["status"] == "ok"
    assert result["network"] == "injected_transport"
    assert result["uri"] == "ws://ops.koreainvestment.com:31000"
    assert result["approval"] == "issued"
    assert result["subscription"] == {"channel": "ccnl_krx", "tr_id": "H0STCNT0", "tr_key": "005930"}
    assert result["received_frames"] == 3
    assert result["pong_frames"] == 1
    assert result["sample_payloads"][0]["tr_id"] == "H0STCNT0"
    assert result["sample_payloads"][0]["event"]["symbol"] == "005930"
    assert transport.urls == ["ws://ops.koreainvestment.com:31000"]
    assert transport.socket.sent_json == [
        {
            "header": {
                "content-type": "utf-8",
                "approval_key": "approval-123",
                "tr_type": "1",
                "custtype": "P",
            },
            "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}},
        }
    ]
    assert transport.socket.pongs == [b'{"header":{"tr_id":"PINGPONG"}}']
    assert transport.socket.closed is True
    assert client.calls[0]["path"] == "/oauth2/Approval"
    assert json.dumps(result["sample_payloads"], sort_keys=True)


def test_kis_websocket_smoke_records_subscription_ack_key_presence() -> None:
    client = _KisClient()
    transport = _NoticeAckKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_notice",
            tr_key="MYHTSID",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "ok"
    assert result["subscription"] == {"channel": "ccnl_notice", "tr_id": "H0STCNI9", "tr_key": "MYHTSID"}
    assert result["received_frames"] == 1
    assert result["subscription_events"] == [
        {
            "tr_id": "H0STCNI9",
            "status": "ok",
            "message": "SUBSCRIBE SUCCESS",
            "encrypted": True,
            "iv_present": True,
            "key_present": True,
        }
    ]
    assert transport.socket.closed is True


def test_kis_websocket_smoke_evidence_redacts_subscription_ack_secrets() -> None:
    result = {
        "status": "ok",
        "connector": "kis",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "ws://ops.koreainvestment.com:31000",
        "approval": "issued",
        "subscription": {"channel": "ccnl_notice", "tr_id": "H0STCNI9", "tr_key": "MYHTSID"},
        "subscription_events": [
            {
                "tr_id": "H0STCNI9",
                "status": "ok",
                "message": "SUBSCRIBE SUCCESS",
                "encrypted": True,
                "tr_key": "MYHTSID",
                "iv": "iv-123",
                "key": "key-123",
                "iv_present": True,
                "key_present": True,
            }
        ],
        "received_frames": 1,
        "pong_frames": 0,
        "sample_payloads": [],
    }

    evidence = kis.websocket_smoke_evidence(result)

    assert evidence["subscription_events"] == [
        {
            "tr_id": "H0STCNI9",
            "status": "ok",
            "message": "SUBSCRIBE SUCCESS",
            "encrypted": True,
            "iv_present": True,
            "key_present": True,
        }
    ]
    serialized = json.dumps(evidence, sort_keys=True)
    assert "MYHTSID" not in serialized
    assert "iv-123" not in serialized
    assert "key-123" not in serialized


def test_kis_websocket_smoke_fails_closed_on_subscription_error_ack() -> None:
    client = _KisClient()
    transport = _NoticeErrorKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_notice",
            tr_key="MYHTSID",
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
            "tr_id": "H0STCNI9",
            "status": "error",
            "message": "SUBSCRIBE DENIED",
            "encrypted": False,
            "iv_present": True,
            "key_present": True,
        }
    ]
    assert "SUBSCRIBE DENIED" in result["reason"]
    assert transport.socket.closed is True


def test_kis_websocket_smoke_with_evidence_writes_subscription_error_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _NoticeErrorKisTransport()
    target = tmp_path / "subscription-error" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_notice",
            tr_key="MYHTSID",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "MYHTSID" not in serialized
    assert "iv-denied" not in serialized
    assert "key-denied" not in serialized


def test_kis_websocket_smoke_fails_closed_on_malformed_frame() -> None:
    client = _KisClient()
    transport = _MalformedFrameKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "malformed-frame" not in json.dumps(result, sort_keys=True)
    assert transport.socket.closed is True


def test_kis_websocket_smoke_with_evidence_writes_frame_error_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _MalformedFrameKisTransport()
    target = tmp_path / "frame-error" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "malformed-frame" not in serialized
    assert "005930" not in serialized


def test_kis_websocket_smoke_rejects_non_positive_max_messages_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=0,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["parameter"] == "max_messages"
    assert result["network"] == "not_attempted"
    assert result["received_frames"] == 0
    assert "positive integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_max_messages_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-max-messages" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_non_positive_message_timeout_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "positive number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_message_timeout_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-message-timeout" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_invalid_connect_attempts_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "positive integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_connect_attempts_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-connect-attempts" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_invalid_reconnect_attempts_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "non-negative integer" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_reconnect_attempts_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-reconnect-attempts" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_invalid_connect_backoff_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "non-negative number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_connect_backoff_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-connect-backoff" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_invalid_reconnect_backoff_before_network() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    assert "non-negative number" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_invalid_reconnect_backoff_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-reconnect-backoff" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_unknown_channel_before_approval() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="unknown_channel",
            tr_key="005930",
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
    assert "supported KIS WebSocket channel" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_unknown_channel_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-channel" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="unknown_channel",
            tr_key="005930",
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
    assert "supported KIS WebSocket channel" in payload["reason"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_smoke_rejects_empty_tr_key_before_approval() -> None:
    client = _KisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
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
    assert "requires a tr_key" in result["reason"]
    assert client.calls == []
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_empty_tr_key_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "invalid-tr-key" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "005930" not in serialized
    assert client.calls == []
    assert transport.urls == []


def test_kis_websocket_transport_adapter_sends_json_receives_pongs_and_closes() -> None:
    socket = _WebSocketClient()
    calls: list[str] = []

    async def connect(url):
        calls.append(url)
        return socket

    async def exercise() -> None:
        transport = kis.KisWebSocketTransport(connect_factory=connect)
        active = await transport.connect("ws://ops.koreainvestment.com:31000")
        await active.send_json({"body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}}})
        assert await active.receive() == b'{"header":{"tr_id":"PINGPONG"}}'
        await active.pong(b'{"header":{"tr_id":"PINGPONG"}}')
        await active.close()

    asyncio.run(exercise())

    assert calls == ["ws://ops.koreainvestment.com:31000"]
    assert json.loads(socket.sent[0]) == {"body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}}}
    assert socket.pongs == [b'{"header":{"tr_id":"PINGPONG"}}']
    assert socket.closed is True


def test_kis_websocket_smoke_uses_default_transport_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _KisClient()
    transport = _KisTransport()
    calls: list[str] = []

    def factory():
        calls.append("factory")
        return transport

    monkeypatch.setattr(kis, "create_websocket_transport", factory)

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            max_messages=3,
        )
    )

    assert result["status"] == "ok"
    assert result["network"] == "websocket_transport"
    assert calls == ["factory"]
    assert transport.urls == ["ws://ops.koreainvestment.com:31000"]
    assert client.calls[0]["path"] == "/oauth2/Approval"


def test_kis_websocket_smoke_returns_approval_error_without_socket_connect() -> None:
    client = _ApprovalFailureKisClient()
    transport = _KisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "approval_error"
    assert result["network"] == "approval_request"
    assert result["approval"] == "failed"
    assert result["received_frames"] == 0
    assert result["pong_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "approval service unavailable" in result["reason"]
    assert client.calls[0]["path"] == "/oauth2/Approval"
    assert transport.urls == []
    assert transport.socket.closed is False


def test_kis_websocket_smoke_with_evidence_writes_approval_error_summary(tmp_path) -> None:
    client = _ApprovalFailureKisClient()
    transport = _KisTransport()
    target = tmp_path / "approval-error" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "approval_error"
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "approval_error"
    assert payload["network"] == "approval_request"
    assert payload["approval"] == "failed"
    assert payload["received_frames"] == 0
    assert payload["subscription"]["tr_key_present"] is False
    assert "approval service unavailable" in payload["reason"]
    assert "005930" not in json.dumps(payload, sort_keys=True)
    assert transport.urls == []


def test_kis_websocket_smoke_retries_connect_failure_before_subscribe() -> None:
    client = _KisClient()
    transport = _FlakyKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=3,
            connect_attempts=2,
            connect_backoff_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["connection_attempts"] == 2
    assert transport.urls == [
        "ws://ops.koreainvestment.com:31000",
        "ws://ops.koreainvestment.com:31000",
    ]
    assert len(transport.socket.sent_json) == 1
    assert transport.socket.closed is True


def test_kis_websocket_smoke_with_evidence_writes_connection_error_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _FailingKisTransport()
    target = tmp_path / "connection-error" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=3,
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


def test_kis_websocket_smoke_reconnects_and_resubscribes_after_receive_drop() -> None:
    client = _KisClient()
    transport = _ReconnectKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=3,
            reconnect_attempts=1,
            reconnect_backoff_seconds=0,
        )
    )

    first_socket, second_socket = transport.sockets
    assert result["status"] == "ok"
    assert result["reconnects"] == 1
    assert result["connection_attempts"] == 2
    assert transport.urls == [
        "ws://ops.koreainvestment.com:31000",
        "ws://ops.koreainvestment.com:31000",
    ]
    assert len(first_socket.sent_json) == 1
    assert first_socket.sent_json == second_socket.sent_json
    assert first_socket.closed is True
    assert second_socket.closed is True


def test_kis_websocket_smoke_with_evidence_writes_reconnect_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _ReconnectKisTransport()
    target = tmp_path / "reconnect" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=3,
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


def test_kis_websocket_smoke_times_out_and_closes_socket() -> None:
    client = _KisClient()
    transport = _HangingKisTransport()

    result = asyncio.run(
        kis.run_websocket_smoke(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            client=client,
            transport=transport,
            max_messages=3,
            message_timeout=0.001,
        )
    )

    assert result["status"] == "timeout"
    assert result["network"] == "injected_transport"
    assert result["received_frames"] == 0
    assert result["pong_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["timeout_seconds"] == 0.001
    assert "message_timeout" in result["reason"]
    assert transport.socket.closed is True


def test_kis_websocket_smoke_with_evidence_writes_timeout_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _HangingKisTransport()
    target = tmp_path / "timeout" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
            tr_key="005930",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=3,
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


def test_kis_websocket_smoke_evidence_redacts_subscription_and_sample_values() -> None:
    result = {
        "status": "ok",
        "connector": "kis",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "ws://ops.koreainvestment.com:31000",
        "approval": "issued",
        "subscription": {"channel": "ccnl_notice", "tr_id": "H0STCNI9", "tr_key": "MYHTSID"},
        "received_frames": 2,
        "pong_frames": 1,
        "sample_payloads": [
            {
                "type": "data",
                "status": "ok",
                "prefix": "1",
                "tr_id": "H0STCNI9",
                "sequence": "001",
                "fields": {"CUST_ID": "MYHTSID", "ACNT_NO": "12345678-01", "STCK_SHRN_ISCD": "005930"},
                "raw_values": ["MYHTSID", "12345678-01", "0000012345"],
                "event": {"symbol": "005930", "account_number": "12345678", "access_token": "secret-token"},
            }
        ],
    }

    evidence = kis.websocket_smoke_evidence(result)

    assert evidence["subscription"] == {
        "channel": "ccnl_notice",
        "tr_id": "H0STCNI9",
        "tr_key_present": True,
        "tr_key_kind": "hts_id",
    }
    assert evidence["sample_count"] == 1
    sample = evidence["sample_payloads"][0]
    assert sample["event"] == {
        "symbol": "005930",
        "account_number": "[redacted]",
        "access_token": "[redacted]",
    }
    assert sample["field_count"] == 3
    assert sample["raw_value_count"] == 3
    assert "fields" not in sample
    assert "raw_values" not in sample
    serialized = json.dumps(evidence, sort_keys=True)
    assert "MYHTSID" not in serialized
    assert "12345678" not in serialized
    assert "secret-token" not in serialized


def test_kis_write_websocket_smoke_evidence_saves_redacted_json(tmp_path) -> None:
    result = {
        "status": "ok",
        "connector": "kis",
        "profile": "paper",
        "environment": "paper",
        "network": "injected_transport",
        "uri": "ws://ops.koreainvestment.com:31000",
        "approval": "issued",
        "subscription": {"channel": "ccnl_notice", "tr_id": "H0STCNI9", "tr_key": "MYHTSID"},
        "received_frames": 2,
        "pong_frames": 1,
        "sample_payloads": [
            {
                "type": "data",
                "status": "ok",
                "prefix": "1",
                "tr_id": "H0STCNI9",
                "sequence": "001",
                "fields": {"CUST_ID": "MYHTSID", "ACNT_NO": "12345678-01"},
                "raw_values": ["MYHTSID", "12345678-01", "0000012345"],
                "event": {"symbol": "005930", "account_number": "12345678", "access_token": "secret-token"},
            }
        ],
    }
    target = tmp_path / "nested" / "kis-websocket-smoke.json"

    written = kis.write_websocket_smoke_evidence(result, target)

    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["subscription"] == {
        "channel": "ccnl_notice",
        "tr_id": "H0STCNI9",
        "tr_key_present": True,
        "tr_key_kind": "hts_id",
    }
    assert payload["sample_payloads"][0]["event"]["access_token"] == "[redacted]"
    serialized = json.dumps(payload, sort_keys=True)
    assert "MYHTSID" not in serialized
    assert "12345678" not in serialized
    assert "secret-token" not in serialized
    assert "raw_values" not in serialized


def test_kis_websocket_smoke_with_evidence_requires_broker_call_opt_in(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_krx",
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


def test_kis_websocket_smoke_with_evidence_blocks_live_without_live_opt_in(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "kis-websocket-smoke-live.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(profile="live"),
            channel="ccnl_krx",
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


def test_kis_websocket_smoke_with_evidence_rejects_directory_path_before_broker_call(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "kis-websocket-smoke-dir"
    target.mkdir()

    try:
        result = asyncio.run(
            kis.run_websocket_smoke_with_evidence(
                _cfg(),
                channel="ccnl_krx",
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


def test_kis_websocket_smoke_with_evidence_rejects_file_parent_before_broker_call(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    parent = tmp_path / "not-a-directory"
    parent.write_text("existing file", encoding="utf-8")
    target = parent / "kis-websocket-smoke.json"

    try:
        result = asyncio.run(
            kis.run_websocket_smoke_with_evidence(
                _cfg(),
                channel="ccnl_krx",
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


def test_kis_websocket_smoke_with_evidence_writes_only_redacted_summary(tmp_path) -> None:
    client = _KisClient()
    transport = _KisTransport()
    target = tmp_path / "nested" / "kis-websocket-smoke.json"

    result = asyncio.run(
        kis.run_websocket_smoke_with_evidence(
            _cfg(),
            channel="ccnl_notice",
            tr_key="MYHTSID",
            evidence_path=target,
            client=client,
            transport=transport,
            allow_broker_calls=True,
            max_messages=3,
        )
    )

    assert result["status"] == "ok"
    assert result["evidence_path"] == str(target)
    assert result["subscription"] == {
        "channel": "ccnl_notice",
        "tr_id": "H0STCNI9",
        "tr_key_present": True,
        "tr_key_kind": "hts_id",
    }
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {key: value for key, value in result.items() if key != "evidence_path"}
    serialized = json.dumps(result, sort_keys=True)
    assert "MYHTSID" not in serialized
    assert "approval-123" not in serialized
    assert "app-secret" not in serialized
    assert "raw_values" not in serialized
    assert client.calls[0]["path"] == "/oauth2/Approval"
    assert transport.urls == ["ws://ops.koreainvestment.com:31000"]


def _kis_notice_values(
    *,
    order_id: str = "0000012345",
    cntg_yn: str = "2",
    acpt_yn: str = "Y",
    rfus_yn: str = "N",
    quantity: str = "3",
    price: str = "70000",
) -> list[str]:
    return [
        "myhtsid",
        "12345678-01",
        order_id,
        "",
        "02",
        "1",
        "00",
        "",
        "005930",
        quantity,
        price,
        "153001",
        rfus_yn,
        cntg_yn,
        acpt_yn,
        "91234",
        "5",
        "TEST ACCOUNT",
        "0",
        "KRX",
        "Y",
        "",
        "",
        "",
        "20260604",
        "70000",
    ]


def test_kis_parse_websocket_order_notices_from_official_notice_fields() -> None:
    assert len(kis.KIS_WEBSOCKET_NOTICE_FIELDS) == 26
    assert kis.KIS_WEBSOCKET_NOTICE_FIELDS[13] == "CNTG_YN"
    assert kis.KIS_WEBSOCKET_NOTICE_FIELDS[-1] == "ODER_PRC"

    frame = "1|H0STCNI9|002|" + "^".join(
        _kis_notice_values(order_id="0000012345")
        + _kis_notice_values(order_id="0000012346", cntg_yn="1", acpt_yn="Y", rfus_yn="N", quantity="0", price="0")
    )

    notices = kis.parse_websocket_order_notices(frame)

    assert len(notices) == 2
    execution = notices[0]
    assert execution["kind"] == "order_notice"
    assert execution["tr_id"] == "H0STCNI9"
    assert execution["environment"] == "paper"
    assert execution["encrypted"] is True
    assert execution["customer_id"] == "myhtsid"
    assert execution["account"] == "12345678-01"
    assert execution["order_id"] == "0000012345"
    assert execution["symbol"] == "005930"
    assert execution["side"] == "buy"
    assert execution["notice_type"] == "execution"
    assert execution["execution_notice"] is True
    assert execution["execution_quantity"] == 3.0
    assert execution["execution_price"] == 70000.0
    assert execution["execution_time"] == "153001"
    assert execution["accepted"] is True
    assert execution["refused"] is False
    assert execution["order_quantity"] == 5.0
    assert execution["order_price"] == 70000.0
    assert execution["execution_date"] == "20260604"
    assert execution["raw_fields"]["CNTG_YN"] == "2"
    assert len(execution["raw_values"]) == 26

    accepted = notices[1]
    assert accepted["notice_type"] == "order_status"
    assert accepted["execution_notice"] is False
    assert accepted["execution_quantity"] == 0.0


def test_kis_order_notice_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="H0STCNI"):
        kis.parse_websocket_order_notices("0|H0STCNT0|001|" + "^".join(_kis_notice_values()))

    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 26 values"):
        kis.parse_websocket_order_notices("1|H0STCNI0|001|" + "^".join(_kis_notice_values()[:-1]))


def test_kis_decrypts_and_parses_encrypted_order_notice_payload() -> None:
    key = "0123456789abcdef0123456789abcdef"
    iv = "abcdef9876543210"
    cipher_text = (
        "lt/2OVlwH03tstNbVo8JvqAP7Q1H5VofgPR5/ydyGcdKlJQBvUZ6T4kWyk9po2co"
        "CEzfjguWetOkVvj+eoPBDZrMWbSaY1zRXr26GyJ9HyYtOR5Sv9PWuFljujIdH6Wg"
        "SYWsXbWclyTYGhdEbeQila4ZXE9CEs+k3grrpKBqVLE="
    )

    payload = kis.decrypt_websocket_payload(cipher_text, key=key, iv=iv)
    assert payload == "^".join(_kis_notice_values())

    notices = kis.parse_websocket_encrypted_order_notices(f"1|H0STCNI9|001|{cipher_text}", key=key, iv=iv)

    assert len(notices) == 1
    assert notices[0]["order_id"] == "0000012345"
    assert notices[0]["execution_notice"] is True
    assert notices[0]["encrypted"] is True
    assert notices[0]["raw_fields"]["CNTG_ISNM40"] == "20260604"


def test_kis_decrypt_rejects_missing_key_or_cleartext_frame() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="key and iv"):
        kis.decrypt_websocket_payload("cipher", key="", iv="abcdef9876543210")

    with pytest.raises(kis.KoreanConnectorConfigError, match="encrypted order notice frame"):
        kis.parse_websocket_encrypted_order_notices("0|H0STCNI9|001|" + "^".join(_kis_notice_values()), key="x", iv="y")


def test_kis_quote_requests_token_and_official_quote_endpoint() -> None:
    client = _KisClient()
    out = kis.get_quote("005930.KS", config=_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "005930"
    assert out["quote"]["last"] == 70000.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/tokenP"
    assert token_call["json"]["appkey"] == "app-key"
    assert quote_call["path"] == "/uapi/domestic-stock/v1/quotations/inquire-price"
    assert quote_call["params"] == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
    assert quote_call["headers"]["authorization"] == "Bearer token-123"
    assert quote_call["headers"]["tr_id"] == "FHKST01010100"


def test_kis_history_uses_daily_itemchartprice_contract() -> None:
    client = _KisClient()
    out = kis.get_historical_bars("KRX:005930", config=_cfg(), client=client, period="1d", limit=1)
    assert out["status"] == "ok"
    assert out["bars"][0]["date"] == "20260604"
    assert out["bars"][0]["close"] == 70000.0

    history_call = client.calls[-1]
    assert history_call["path"] == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    assert history_call["headers"]["tr_id"] == "FHKST03010100"
    assert history_call["params"]["FID_PERIOD_DIV_CODE"] == "D"
    assert history_call["params"]["FID_INPUT_ISCD"] == "005930"


def test_kis_account_snapshot_uses_paper_balance_tr_id() -> None:
    client = _KisClient()
    out = kis.get_account_snapshot(_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["positions"][0]["symbol"] == "005930"
    assert out["account"]["cash"] == 500000.0

    balance_call = client.calls[-1]
    assert balance_call["path"] == "/uapi/domestic-stock/v1/trading/inquire-balance"
    assert balance_call["headers"]["tr_id"] == "VTTC8434R"
    assert balance_call["params"]["CANO"] == "12345678"
    assert balance_call["params"]["ACNT_PRDT_CD"] == "01"


def test_kis_open_orders_use_psbl_rvsecncl_contract() -> None:
    client = _KisClient()
    out = kis.get_open_orders(_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["orders"] == [
        {
            "order_id": "00001",
            "broker_order_id": "91234:00001",
            "symbol": "005930",
            "side": "buy",
            "quantity": 5.0,
            "filled_quantity": 2.0,
            "remaining_quantity": 3.0,
            "cancelable_quantity": 3.0,
            "limit_price": 70000.0,
            "raw": {
                "odno": "00001",
                "ord_gno_brno": "91234",
                "pdno": "005930",
                "ord_qty": "5",
                "tot_ccld_qty": "2",
                "psbl_qty": "3",
                "sll_buy_dvsn_cd": "02",
                "ord_unpr": "70000",
            },
        }
    ]

    call = client.calls[-1]
    assert call["path"] == "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    assert call["headers"]["tr_id"] == "TTTC0084R"
    assert call["params"] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "INQR_DVSN_1": "1",
        "INQR_DVSN_2": "0",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }


def test_kis_place_order_hashes_and_posts_order_cash() -> None:
    client = _KisClient()
    out = kis.place_order(
        _cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
    )
    assert out["status"] == "ok"
    assert out["order_id"] == "00001"

    hash_call = client.calls[-2]
    order_call = client.calls[-1]
    assert hash_call["path"] == "/uapi/hashkey"
    assert order_call["path"] == "/uapi/domestic-stock/v1/trading/order-cash"
    assert order_call["headers"]["hashkey"] == "hash-123"
    assert order_call["headers"]["tr_id"] == "VTTC0012U"
    assert order_call["json"]["PDNO"] == "005930"
    assert order_call["json"]["ORD_DVSN"] == "00"
    assert order_call["json"]["ORD_QTY"] == "3"
    assert order_call["json"]["ORD_UNPR"] == "70000"


def test_kis_live_order_uses_live_sell_tr_id() -> None:
    client = _KisClient()
    kis.place_order(
        _cfg(profile="live"),
        symbol="005930",
        side="sell",
        quantity=1,
        order_type="market",
        client=client,
    )
    order_call = client.calls[-1]
    assert order_call["headers"]["tr_id"] == "TTTC0011U"
    assert order_call["json"]["ORD_DVSN"] == "01"
    assert order_call["json"]["ORD_UNPR"] == "0"


def test_kis_cancel_order_posts_rvsecncl_contract() -> None:
    client = _KisClient()
    out = kis.cancel_order(_cfg(), "91234:00001", client=client)
    assert out["status"] == "ok"

    cancel_call = client.calls[-1]
    assert cancel_call["path"] == "/uapi/domestic-stock/v1/trading/order-rvsecncl"
    assert cancel_call["headers"]["tr_id"] == "VTTC0013U"
    assert cancel_call["json"]["KRX_FWDG_ORD_ORGNO"] == "91234"
    assert cancel_call["json"]["ORGN_ODNO"] == "00001"
    assert cancel_call["json"]["RVSE_CNCL_DVSN_CD"] == "02"
    assert cancel_call["json"]["QTY_ALL_ORD_YN"] == "Y"
