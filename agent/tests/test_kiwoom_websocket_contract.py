"""Kiwoom official REST WebSocket contract tests.

These tests pin only the WebSocket URL and JSON frames shown in Kiwoom's
official REST API "Web Socket" guide. They do not open a real socket or require
live credentials.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.trading.connectors.kr_common import KoreanConnectorConfig
from src.trading.connectors.kiwoom import sdk as kiwoom

pytestmark = pytest.mark.unit


def test_kiwoom_websocket_catalog_matches_official_realtime_sample() -> None:
    endpoint = kiwoom.KIWOOM_WEBSOCKET_ENDPOINTS["domestic_stock_realtime"]

    assert endpoint["url"] == "wss://api.kiwoom.com:10000/api/dostk/websocket"
    assert endpoint["login_trnm"] == "LOGIN"
    assert endpoint["subscribe_trnm"] == "REG"
    assert endpoint["ping_trnm"] == "PING"
    assert endpoint["sample_type"] == "0B"


def test_kiwoom_websocket_condition_list_contract_matches_official_sample() -> None:
    assert kiwoom.KIWOOM_WEBSOCKET_CONDITION_TRS["condition_list"] == {
        "api_id": "ka10171",
        "trnm": "CNSRLST",
        "description": "조건검색 목록조회",
    }
    assert kiwoom.build_websocket_condition_list_frame() == {"trnm": "CNSRLST"}

    parsed = kiwoom.parse_websocket_condition_list(
        {
            "trnm": "CNSRLST",
            "return_code": 0,
            "return_msg": "",
            "data": [["0", "조건1"], ["1", "조건2"]],
        }
    )

    assert parsed == [{"seq": "0", "name": "조건1"}, {"seq": "1", "name": "조건2"}]

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="condition list failed"):
        kiwoom.parse_websocket_condition_list({"trnm": "CNSRLST", "return_code": 1, "return_msg": "bad request"})


def test_kiwoom_websocket_condition_request_contract_matches_official_sample() -> None:
    request = kiwoom.KIWOOM_WEBSOCKET_CONDITION_REQUEST_TRS["general"]

    assert request == {
        "api_id": "ka10172",
        "trnm": "CNSRREQ",
        "search_type": "0",
        "stex_tp": "K",
        "description": "조건검색 요청 일반",
    }
    assert kiwoom.build_websocket_condition_request_frame("4") == {
        "trnm": "CNSRREQ",
        "seq": "4",
        "search_type": "0",
        "stex_tp": "K",
        "cont_yn": "N",
        "next_key": "",
    }

    parsed = kiwoom.parse_websocket_condition_request_response(
        {
            "trnm": "CNSRREQ",
            "seq": "4",
            "cont_yn": "Y",
            "next_key": "next-key",
            "return_code": 0,
            "return_msg": "",
            "data": [
                {
                    "9001": "A005930",
                    "302": "삼성전자",
                    "10": "+000071000",
                    "25": "2",
                    "11": "+000001000",
                    "12": "000001500",
                    "13": "000123456",
                    "16": "+000070000",
                    "17": "+000072000",
                    "18": "+000069000",
                }
            ],
        }
    )

    assert parsed == {
        "seq": "4",
        "cont_yn": "Y",
        "next_key": "next-key",
        "results": [
            {
                "symbol": "005930",
                "raw_symbol": "A005930",
                "name": "삼성전자",
                "current_price": "+000071000",
                "change_sign": "2",
                "change": "+000001000",
                "change_rate": "000001500",
                "volume": "000123456",
                "open": "+000070000",
                "high": "+000072000",
                "low": "+000069000",
                "raw": {
                    "9001": "A005930",
                    "302": "삼성전자",
                    "10": "+000071000",
                    "25": "2",
                    "11": "+000001000",
                    "12": "000001500",
                    "13": "000123456",
                    "16": "+000070000",
                    "17": "+000072000",
                    "18": "+000069000",
                },
            }
        ],
        "raw": {
            "trnm": "CNSRREQ",
            "seq": "4",
            "cont_yn": "Y",
            "next_key": "next-key",
            "return_code": 0,
            "return_msg": "",
            "data": [
                {
                    "9001": "A005930",
                    "302": "삼성전자",
                    "10": "+000071000",
                    "25": "2",
                    "11": "+000001000",
                    "12": "000001500",
                    "13": "000123456",
                    "16": "+000070000",
                    "17": "+000072000",
                    "18": "+000069000",
                }
            ],
        },
    }

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="condition request failed"):
        kiwoom.parse_websocket_condition_request_response({"trnm": "CNSRREQ", "return_code": 1, "return_msg": "bad seq"})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected CNSRREQ"):
        kiwoom.parse_websocket_condition_request_response({"trnm": "CNSRLST", "return_code": 0})


def test_kiwoom_websocket_condition_realtime_contract_matches_official_sample() -> None:
    request = kiwoom.KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS["subscribe"]

    assert request == {
        "api_id": "ka10173",
        "trnm": "CNSRREQ",
        "search_type": "1",
        "stex_tp": "K",
        "realtime_trnm": "REAL",
        "description": "조건검색 요청 실시간",
    }
    assert kiwoom.build_websocket_condition_realtime_frame("4") == {
        "trnm": "CNSRREQ",
        "seq": "4",
        "search_type": "1",
        "stex_tp": "K",
    }

    registered = kiwoom.parse_websocket_condition_realtime_response(
        {
            "trnm": "CNSRREQ",
            "seq": "4",
            "return_code": 0,
            "return_msg": "",
            "data": [{"jmcode": "A005930"}, {"jmcode": "Q123456"}],
        }
    )

    assert registered == {
        "seq": "4",
        "symbols": ["005930", "123456"],
        "raw_symbols": ["A005930", "Q123456"],
        "raw": {
            "trnm": "CNSRREQ",
            "seq": "4",
            "return_code": 0,
            "return_msg": "",
            "data": [{"jmcode": "A005930"}, {"jmcode": "Q123456"}],
        },
    }

    realtime = kiwoom.parse_websocket_condition_realtime_message(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "0A",
                    "name": "005930",
                    "values": {
                        "841": "4",
                        "9001": "005930",
                        "843": "I",
                        "20": "091500",
                        "907": "2",
                    },
                }
            ],
        }
    )

    assert realtime == [
        {
            "type": "0A",
            "name": "005930",
            "seq": "4",
            "symbol": "005930",
            "action": "I",
            "trade_time": "091500",
            "side": "2",
            "values": {
                "841": "4",
                "9001": "005930",
                "843": "I",
                "20": "091500",
                "907": "2",
            },
            "raw": {
                "type": "0A",
                "name": "005930",
                "values": {
                    "841": "4",
                    "9001": "005930",
                    "843": "I",
                    "20": "091500",
                    "907": "2",
                },
            },
        }
    ]

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="condition realtime request failed"):
        kiwoom.parse_websocket_condition_realtime_response({"trnm": "CNSRREQ", "return_code": 1, "return_msg": "bad seq"})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected REAL"):
        kiwoom.parse_websocket_condition_realtime_message({"trnm": "CNSRREQ", "return_code": 0})


def test_kiwoom_websocket_condition_unsubscribe_contract_matches_official_sample() -> None:
    unsubscribe = kiwoom.KIWOOM_WEBSOCKET_CONDITION_UNSUBSCRIBE_TRS["unsubscribe"]

    assert unsubscribe == {
        "api_id": "ka10174",
        "method": "POST",
        "path": "/api/dostk/websocket",
        "trnm": "CNSRCLR",
        "description": "조건검색 실시간 해제",
    }
    assert kiwoom.build_websocket_condition_unsubscribe_frame("1") == {
        "trnm": "CNSRCLR",
        "seq": "1",
    }
    assert kiwoom.parse_websocket_condition_unsubscribe_response(
        {"return_code": 0, "return_msg": "", "trnm": "CNSRCLR", "seq": "1"}
    ) == {
        "status": "ok",
        "seq": "1",
        "raw": {"return_code": 0, "return_msg": "", "trnm": "CNSRCLR", "seq": "1"},
    }

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="condition sequence"):
        kiwoom.build_websocket_condition_unsubscribe_frame("")

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="unexpected Kiwoom condition unsubscribe TR"):
        kiwoom.parse_websocket_condition_unsubscribe_response({"return_code": 0, "trnm": "CNSRREQ", "seq": "1"})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="Kiwoom condition unsubscribe failed"):
        kiwoom.parse_websocket_condition_unsubscribe_response(
            {"return_code": 1, "return_msg": "not registered", "trnm": "CNSRCLR", "seq": "1"}
        )


def test_kiwoom_websocket_realtime_types_match_official_catalog() -> None:
    assert kiwoom.KIWOOM_WEBSOCKET_REALTIME_TYPES["0B"] == "주식체결"
    assert kiwoom.KIWOOM_WEBSOCKET_REALTIME_TYPES["0D"] == "주식호가잔량"
    assert kiwoom.KIWOOM_WEBSOCKET_REALTIME_TYPES["0H"] == "주식예상체결"
    assert kiwoom.KIWOOM_WEBSOCKET_REALTIME_TYPES["1h"] == "VI발동/해제"

    frame = kiwoom.build_websocket_subscribe_frame(["039490"], types=["0B", "0D"])

    assert frame["data"] == [{"item": ["039490"], "type": ["0B", "0D"]}]

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="Unknown Kiwoom WebSocket realtime type"):
        kiwoom.build_websocket_subscribe_frame(["039490"], types=["BAD"])


def test_kiwoom_websocket_orderbook_fields_match_official_0d_catalog() -> None:
    assert len(kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS) == 163
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["21"] == "호가시간"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["41"] == "매도호가1"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["51"] == "매수호가1"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["121"] == "매도호가총잔량"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["125"] == "매수호가총잔량"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["6044"] == "KRX 매도호가잔량1"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["6066"] == "NXT 매도호가잔량1"
    assert kiwoom.KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS["6115"] == "NXT중간가대비등락율"


def test_kiwoom_websocket_orderbook_parser_matches_official_0d_sample() -> None:
    parsed = kiwoom.parse_websocket_orderbook_snapshots(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "0D",
                    "name": "주식호가잔량",
                    "item": "005930",
                    "values": {
                        "21": "165207",
                        "41": "-20800",
                        "61": "82",
                        "81": "0",
                        "51": "-20700",
                        "71": "23847",
                        "91": "0",
                        "42": "+20900",
                        "62": "393",
                        "82": "0",
                        "52": "-20650",
                        "72": "834748",
                        "92": "0",
                        "50": "+21350",
                        "70": "1242991",
                        "60": "-20250",
                        "80": "1062405",
                        "121": "12622527",
                        "122": "-1036021",
                        "125": "14453430",
                        "126": "+1062126",
                        "23": "20850",
                        "24": "332941",
                        "128": "+1830903",
                        "129": "114.51",
                        "138": "-1830903",
                        "139": "87.33",
                        "13": "30379650",
                        "299": "-1.06",
                        "6044": "0",
                        "6054": "0",
                        "6066": "0",
                        "6076": "0",
                        "6102": "0",
                        "6107": "0",
                    },
                }
            ],
        }
    )

    assert len(parsed) == 1
    snapshot = parsed[0]
    assert snapshot["type"] == "0D"
    assert snapshot["name"] == "주식호가잔량"
    assert snapshot["symbol"] == "005930"
    assert snapshot["time"] == "165207"
    assert snapshot["asks"][:2] == [
        {"level": 1, "price": 20800.0, "quantity": 82.0, "change": 0.0, "krx_quantity": 0.0, "nxt_quantity": 0.0, "lp_quantity": None},
        {"level": 2, "price": 20900.0, "quantity": 393.0, "change": 0.0, "krx_quantity": None, "nxt_quantity": None, "lp_quantity": None},
    ]
    assert snapshot["bids"][:2] == [
        {
            "level": 1,
            "price": 20700.0,
            "quantity": 23847.0,
            "change": 0.0,
            "krx_quantity": 0.0,
            "nxt_quantity": 0.0,
            "lp_quantity": None,
        },
        {
            "level": 2,
            "price": 20650.0,
            "quantity": 834748.0,
            "change": 0.0,
            "krx_quantity": None,
            "nxt_quantity": None,
            "lp_quantity": None,
        },
    ]
    assert len(snapshot["asks"]) == 10
    assert len(snapshot["bids"]) == 10
    assert snapshot["total_ask_quantity"] == 12622527.0
    assert snapshot["total_bid_quantity"] == 14453430.0
    assert snapshot["total_ask_change"] == -1036021.0
    assert snapshot["total_bid_change"] == 1062126.0
    assert snapshot["expected_price"] == 20850.0
    assert snapshot["expected_quantity"] == 332941.0
    assert snapshot["net_bid_quantity"] == 1830903.0
    assert snapshot["bid_ratio"] == 114.51
    assert snapshot["net_ask_quantity"] == -1830903.0
    assert snapshot["ask_ratio"] == 87.33
    assert snapshot["cumulative_volume"] == 30379650.0
    assert snapshot["expected_volume_rate"] == -1.06
    assert snapshot["krx_mid_price"] == 0.0
    assert snapshot["nxt_mid_price"] == 0.0
    assert snapshot["raw_values"]["41"] == "-20800"


def test_kiwoom_websocket_orderbook_parser_rejects_wrong_realtime_shape() -> None:
    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected REAL"):
        kiwoom.parse_websocket_orderbook_snapshots({"trnm": "REG", "return_code": 0})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected type 0D"):
        kiwoom.parse_websocket_orderbook_snapshots({"trnm": "REAL", "data": [{"type": "0B", "values": {}}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="values mapping"):
        kiwoom.parse_websocket_orderbook_snapshots({"trnm": "REAL", "data": [{"type": "0D"}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="data mappings"):
        kiwoom.parse_websocket_orderbook_snapshots({"trnm": "REAL", "data": ["bad"]})


def test_kiwoom_websocket_trade_fields_match_official_0b_catalog() -> None:
    assert kiwoom.KIWOOM_WEBSOCKET_TRADE_FIELDS["20"] == "체결시간"
    assert kiwoom.KIWOOM_WEBSOCKET_TRADE_FIELDS["10"] == "현재가"
    assert kiwoom.KIWOOM_WEBSOCKET_TRADE_FIELDS["15"] == "거래량"
    assert kiwoom.KIWOOM_WEBSOCKET_TRADE_FIELDS["9081"] == "거래소구분"


def test_kiwoom_websocket_trade_tick_parser_matches_official_0b_sample() -> None:
    parsed = kiwoom.parse_websocket_trade_ticks(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "0B",
                    "name": "주식체결",
                    "item": "005930",
                    "values": {
                        "20": "165208",
                        "10": "-20800",
                        "11": "-50",
                        "12": "-0.24",
                        "27": "-20800",
                        "28": "-20700",
                        "15": "+82",
                        "13": "30379732",
                        "14": "632640",
                        "16": "20850",
                        "17": "+21150",
                        "18": "-20450",
                        "25": "5",
                        "228": "98.92",
                        "311": "17230",
                        "290": "2",
                        "9081": "1",
                    },
                }
            ],
        }
    )

    assert parsed == [
        {
            "type": "0B",
            "name": "주식체결",
            "symbol": "005930",
            "time": "165208",
            "last": 20800.0,
            "change": -50.0,
            "change_rate": -0.24,
            "best_ask": 20800.0,
            "best_bid": 20700.0,
            "trade_volume": 82.0,
            "signed_trade_volume": 82.0,
            "trade_side": "buy",
            "cumulative_volume": 30379732.0,
            "cumulative_value_million_krw": 632640.0,
            "open": 20850.0,
            "high": 21150.0,
            "low": 20450.0,
            "change_sign": "5",
            "trade_strength": 98.92,
            "market_cap_100m_krw": 17230.0,
            "session_code": "2",
            "exchange_code": "1",
            "raw_values": {
                "20": "165208",
                "10": "-20800",
                "11": "-50",
                "12": "-0.24",
                "27": "-20800",
                "28": "-20700",
                "15": "+82",
                "13": "30379732",
                "14": "632640",
                "16": "20850",
                "17": "+21150",
                "18": "-20450",
                "25": "5",
                "228": "98.92",
                "311": "17230",
                "290": "2",
                "9081": "1",
            },
            "raw": {
                "type": "0B",
                "name": "주식체결",
                "item": "005930",
                "values": {
                    "20": "165208",
                    "10": "-20800",
                    "11": "-50",
                    "12": "-0.24",
                    "27": "-20800",
                    "28": "-20700",
                    "15": "+82",
                    "13": "30379732",
                    "14": "632640",
                    "16": "20850",
                    "17": "+21150",
                    "18": "-20450",
                    "25": "5",
                    "228": "98.92",
                    "311": "17230",
                    "290": "2",
                    "9081": "1",
                },
            },
        }
    ]


def test_kiwoom_websocket_trade_tick_parser_rejects_wrong_realtime_shape() -> None:
    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected REAL"):
        kiwoom.parse_websocket_trade_ticks({"trnm": "REG", "return_code": 0})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected type 0B"):
        kiwoom.parse_websocket_trade_ticks({"trnm": "REAL", "data": [{"type": "0D", "values": {}}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="values mapping"):
        kiwoom.parse_websocket_trade_ticks({"trnm": "REAL", "data": [{"type": "0B"}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="data mappings"):
        kiwoom.parse_websocket_trade_ticks({"trnm": "REAL", "data": ["bad"]})


def test_kiwoom_websocket_best_quote_fields_match_official_0c_catalog() -> None:
    assert kiwoom.KIWOOM_WEBSOCKET_BEST_QUOTE_FIELDS == {
        "27": "(최우선)매도호가",
        "28": "(최우선)매수호가",
    }


def test_kiwoom_websocket_best_quote_parser_matches_official_0c_sample() -> None:
    parsed = kiwoom.parse_websocket_best_quotes(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "0C",
                    "name": "주식우선호가",
                    "item": "005930",
                    "values": {
                        "27": "-20800",
                        "28": "-20700",
                    },
                }
            ],
        }
    )

    assert parsed == [
        {
            "type": "0C",
            "name": "주식우선호가",
            "symbol": "005930",
            "best_ask": 20800.0,
            "best_bid": 20700.0,
            "raw_values": {
                "27": "-20800",
                "28": "-20700",
            },
            "raw": {
                "type": "0C",
                "name": "주식우선호가",
                "item": "005930",
                "values": {
                    "27": "-20800",
                    "28": "-20700",
                },
            },
        }
    ]


def test_kiwoom_websocket_best_quote_parser_rejects_wrong_realtime_shape() -> None:
    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected REAL"):
        kiwoom.parse_websocket_best_quotes({"trnm": "REG", "return_code": 0})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="expected type 0C"):
        kiwoom.parse_websocket_best_quotes({"trnm": "REAL", "data": [{"type": "0D", "values": {}}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="values mapping"):
        kiwoom.parse_websocket_best_quotes({"trnm": "REAL", "data": [{"type": "0C"}]})

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="data mappings"):
        kiwoom.parse_websocket_best_quotes({"trnm": "REAL", "data": ["bad"]})


def test_kiwoom_websocket_login_and_subscribe_frames_match_official_sample() -> None:
    assert kiwoom.build_websocket_login_frame("access-token") == {"trnm": "LOGIN", "token": "access-token"}

    frame = kiwoom.build_websocket_subscribe_frame(["KRX:039490", "005930.KS"], group_no=1, channel="domestic_stock_realtime")

    assert frame == {
        "trnm": "REG",
        "grp_no": "1",
        "refresh": "1",
        "data": [
            {
                "item": ["039490", "005930"],
                "type": ["0B"],
            }
        ],
    }


def test_kiwoom_websocket_control_frames_are_fail_closed_and_ping_echoes() -> None:
    assert kiwoom.websocket_control_reply({"trnm": "PING", "time": "20260605120000"}) == {
        "trnm": "PING",
        "time": "20260605120000",
    }
    assert kiwoom.websocket_control_reply({"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"}) is None

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="Kiwoom WebSocket login failed"):
        kiwoom.websocket_control_reply({"trnm": "LOGIN", "return_code": 1, "return_msg": "bad token"})


def test_kiwoom_websocket_frames_reject_missing_inputs() -> None:
    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="access token"):
        kiwoom.build_websocket_login_frame("")

    with pytest.raises(kiwoom.KoreanConnectorConfigError, match="at least one symbol"):
        kiwoom.build_websocket_subscribe_frame([])


class _FakeKiwoomWebSocketTransport:
    def __init__(self) -> None:
        self.uri = ""
        self.sent: list[dict] = []
        self._incoming = [
            {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
            {"trnm": "PING", "time": "20260605120000"},
            {"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]},
        ]

    async def connect(self, uri: str) -> "_FakeKiwoomWebSocketTransport":
        self.uri = uri
        return self

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> dict:
        return self._incoming.pop(0)

    async def close(self) -> None:
        self.sent.append({"closed": True})


class _HangingKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    async def receive_json(self) -> dict:
        await asyncio.sleep(1)
        return {}


class _SubscriptionAckKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    def __init__(self) -> None:
        super().__init__()
        self._incoming = [
            {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
            {
                "trnm": "REG",
                "return_code": 0,
                "return_msg": "SUBSCRIBE SUCCESS",
                "grp_no": "1",
                "data": [{"item": ["039490"], "type": ["0B"]}],
            },
            {"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]},
        ]


class _SubscriptionErrorKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    def __init__(self) -> None:
        super().__init__()
        self._incoming = [
            {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
            {
                "trnm": "REG",
                "return_code": 900,
                "return_msg": "SUBSCRIBE FAIL",
                "grp_no": "1",
                "data": [{"item": ["039490"], "type": ["0B"]}],
            },
        ]


class _FrameErrorKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    def __init__(self) -> None:
        super().__init__()
        self._incoming = [
            {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
            {
                "type": "error",
                "status": "error",
                "error": "malformed Kiwoom WebSocket frame",
                "raw": "039490 secret-token",
            },
        ]


class _FlakyKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    async def connect(self, uri: str) -> "_FlakyKiwoomWebSocketTransport":
        self.urls.append(uri)
        if len(self.urls) == 1:
            raise OSError("temporary connect failure")
        return await super().connect(uri)


class _FailingKiwoomWebSocketTransport(_FakeKiwoomWebSocketTransport):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    async def connect(self, uri: str) -> "_FailingKiwoomWebSocketTransport":
        self.urls.append(uri)
        raise OSError("temporary connect failure")


class _KiwoomReconnectSocket:
    def __init__(self, incoming: list[dict]) -> None:
        self.sent: list[dict] = []
        self.closed = False
        self._incoming = list(incoming)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> dict:
        if not self._incoming:
            raise OSError("temporary receive drop")
        return self._incoming.pop(0)

    async def close(self) -> None:
        self.closed = True


class _ReconnectKiwoomWebSocketTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.sockets = [
            _KiwoomReconnectSocket(
                [
                    {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
                    {"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]},
                ]
            ),
            _KiwoomReconnectSocket(
                [
                    {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"},
                    {"trnm": "REAL", "data": [{"item": "005930", "type": "0B"}]},
                ]
            ),
        ]

    async def connect(self, uri: str) -> _KiwoomReconnectSocket:
        self.urls.append(uri)
        return self.sockets[len(self.urls) - 1]


class _WebSocketClient:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.messages: list[str | bytes] = [
            '{"trnm":"LOGIN","return_code":0,"return_msg":"OK"}',
            b'{"trnm":"REAL","data":[{"item":"039490","type":"0B"}]}',
        ]

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str | bytes:
        return self.messages.pop(0)

    async def close(self) -> None:
        self.closed = True


def _kiwoom_ws_cfg(access_token: str | None = "access-token", *, profile: str = "paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(
        connector="kiwoom",
        profile=profile,
        app_key="app-key",
        app_secret="app-secret",
        access_token=access_token,
        paper_url=kiwoom.PAPER_URL,
        live_url=kiwoom.LIVE_URL,
    )


def test_kiwoom_websocket_smoke_is_not_configured_without_access_token() -> None:
    result = asyncio.run(kiwoom.run_websocket_smoke(_kiwoom_ws_cfg(access_token=""), symbols=["039490"]))

    assert result["status"] == "not_configured"
    assert result["connector"] == "kiwoom"
    assert "access_token" in result["missing"]
    assert result["network"] == "not_attempted"


@pytest.mark.parametrize("max_messages", [0, -1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_message_limit(max_messages: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            max_messages=max_messages,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "max_messages"
    assert result["requested_value"] == max_messages
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "positive integer" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_invalid_message_limit(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "invalid-message-limit" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            max_messages=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "max_messages"
    assert result["requested_value"] == 0
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["network"] == "not_attempted"
    assert payload["parameter"] == "max_messages"
    assert payload["requested_value"] == 0
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("message_timeout", [0, -1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_timeout(message_timeout: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            message_timeout=message_timeout,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "message_timeout"
    assert result["requested_value"] == message_timeout
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "positive number" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_invalid_timeout(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "invalid-timeout" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            message_timeout=0,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "message_timeout"
    assert result["requested_value"] == 0
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["network"] == "not_attempted"
    assert payload["parameter"] == "message_timeout"
    assert payload["requested_value"] == 0
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("connect_attempts", [0, -1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_connect_attempts(connect_attempts: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            connect_attempts=connect_attempts,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "connect_attempts"
    assert result["requested_value"] == connect_attempts
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "positive integer" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("reconnect_attempts", [-1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_reconnect_attempts(reconnect_attempts: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            reconnect_attempts=reconnect_attempts,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "reconnect_attempts"
    assert result["requested_value"] == reconnect_attempts
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "non-negative integer" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_invalid_attempts(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "invalid-attempts" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            reconnect_attempts=-1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "reconnect_attempts"
    assert result["requested_value"] == -1
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["network"] == "not_attempted"
    assert payload["parameter"] == "reconnect_attempts"
    assert payload["requested_value"] == -1
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("connect_backoff_seconds", [-0.1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_connect_backoff(connect_backoff_seconds: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            connect_backoff_seconds=connect_backoff_seconds,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "connect_backoff_seconds"
    assert result["requested_value"] == connect_backoff_seconds
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "non-negative number" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("reconnect_backoff_seconds", [-0.1, "bad"])
def test_kiwoom_websocket_smoke_rejects_invalid_reconnect_backoff(reconnect_backoff_seconds: object) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            reconnect_backoff_seconds=reconnect_backoff_seconds,  # type: ignore[arg-type]
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "reconnect_backoff_seconds"
    assert result["requested_value"] == reconnect_backoff_seconds
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "non-negative number" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_invalid_backoff(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "invalid-backoff" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            reconnect_backoff_seconds=-0.1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "reconnect_backoff_seconds"
    assert result["requested_value"] == -0.1
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["network"] == "not_attempted"
    assert payload["parameter"] == "reconnect_backoff_seconds"
    assert payload["requested_value"] == -0.1
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert transport.uri == ""
    assert transport.sent == []


@pytest.mark.parametrize("symbols", [[], ["", " "]])
def test_kiwoom_websocket_smoke_rejects_empty_symbols(symbols: list[str]) -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=symbols,
            transport=transport,
            max_messages=1,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "symbols"
    assert result["requested_value"] == symbols
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["subscription_events"] == []
    assert result["frame_errors"] == []
    assert "at least one symbol" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_empty_symbols(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "invalid-symbols" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=[],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            max_messages=1,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "symbols"
    assert result["requested_value"] == []
    assert result["evidence_path"] == str(target)
    assert payload["status"] == "invalid_request"
    assert payload["network"] == "not_attempted"
    assert payload["parameter"] == "symbols"
    assert payload["requested_value"] == []
    assert "at least one symbol" in payload["reason"]
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_directory_path_before_network(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "directory-target"
    target.mkdir()

    try:
        result = asyncio.run(
            kiwoom.run_websocket_smoke_with_evidence(
                _kiwoom_ws_cfg(),
                symbols=["KRX:039490"],
                evidence_path=target,
                transport=transport,
                allow_broker_calls=True,
                max_messages=1,
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
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_with_evidence_rejects_file_parent_before_network(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    parent = tmp_path / "not-a-directory"
    parent.write_text("existing file", encoding="utf-8")
    target = parent / "kiwoom-websocket-smoke.json"

    try:
        result = asyncio.run(
            kiwoom.run_websocket_smoke_with_evidence(
                _kiwoom_ws_cfg(),
                symbols=["KRX:039490"],
                evidence_path=target,
                transport=transport,
                allow_broker_calls=True,
                max_messages=1,
            )
        )
    except OSError:
        result = {"status": "raised", "network": "broker_called"}

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert result["parameter"] == "evidence_path"
    assert str(parent) in result["requested_value"]
    assert "parent directory" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_smoke_uses_official_frames_with_injected_transport() -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(kiwoom.run_websocket_smoke(_kiwoom_ws_cfg(), symbols=["KRX:039490"], transport=transport))

    assert result["status"] == "ok"
    assert result["network"] == "injected_transport"
    assert result["uri"] == "wss://api.kiwoom.com:10000/api/dostk/websocket"
    assert result["login"] == "ok"
    assert result["subscription"] == {"items": ["039490"], "types": ["0B"]}
    assert result["received_frames"] == 3
    assert result["sample_payloads"] == [{"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]}]
    assert transport.sent[:3] == [
        {"trnm": "LOGIN", "token": "access-token"},
        {
            "trnm": "REG",
            "grp_no": "1",
            "refresh": "1",
            "data": [{"item": ["039490"], "type": ["0B"]}],
        },
        {"trnm": "PING", "time": "20260605120000"},
    ]
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_rejects_unknown_channel_before_network() -> None:
    transport = _FakeKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            channel="bogus",
            symbols=["KRX:039490"],
            transport=transport,
        )
    )

    assert result["status"] == "invalid_request"
    assert result["network"] == "not_attempted"
    assert result["parameter"] == "channel"
    assert result["requested_value"] == "bogus"
    assert "Unknown Kiwoom WebSocket channel" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []


def test_kiwoom_websocket_transport_adapter_sends_json_receives_json_and_closes() -> None:
    socket = _WebSocketClient()
    calls: list[str] = []

    async def connect(url: str) -> _WebSocketClient:
        calls.append(url)
        return socket

    async def exercise() -> None:
        transport = kiwoom.KiwoomWebSocketTransport(connect_factory=connect)
        active = await transport.connect("wss://api.kiwoom.com:10000/api/dostk/websocket")
        await active.send_json({"trnm": "LOGIN", "token": "access-token"})
        assert await active.receive_json() == {"trnm": "LOGIN", "return_code": 0, "return_msg": "OK"}
        assert await active.receive_json() == {"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]}
        await active.close()

    asyncio.run(exercise())

    assert calls == ["wss://api.kiwoom.com:10000/api/dostk/websocket"]
    assert json.loads(socket.sent[0]) == {"trnm": "LOGIN", "token": "access-token"}
    assert socket.closed is True


def test_kiwoom_websocket_transport_adapter_returns_frame_error_for_malformed_json() -> None:
    socket = _WebSocketClient()
    socket.messages = ["not-json"]

    async def connect(url: str) -> _WebSocketClient:
        return socket

    async def exercise() -> dict:
        transport = kiwoom.KiwoomWebSocketTransport(connect_factory=connect)
        active = await transport.connect("wss://api.kiwoom.com:10000/api/dostk/websocket")
        return await active.receive_json()

    frame = asyncio.run(exercise())

    assert frame["type"] == "error"
    assert frame["status"] == "error"
    assert "Expecting value" in frame["error"]


def test_kiwoom_websocket_smoke_uses_default_transport_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    calls: list[str] = []

    def factory() -> _FakeKiwoomWebSocketTransport:
        calls.append("factory")
        return transport

    monkeypatch.setattr(kiwoom, "create_websocket_transport", factory)

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            max_messages=3,
        )
    )

    assert result["status"] == "ok"
    assert result["network"] == "websocket_transport"
    assert calls == ["factory"]
    assert transport.uri == "wss://api.kiwoom.com:10000/api/dostk/websocket"


def test_kiwoom_websocket_smoke_times_out_and_closes_socket() -> None:
    transport = _HangingKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            max_messages=3,
            message_timeout=0.001,
        )
    )

    assert result["status"] == "timeout"
    assert result["network"] == "injected_transport"
    assert result["received_frames"] == 0
    assert result["sample_payloads"] == []
    assert result["timeout_seconds"] == 0.001
    assert "message_timeout" in result["reason"]
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_with_evidence_writes_timeout_summary(tmp_path) -> None:
    transport = _HangingKiwoomWebSocketTransport()
    target = tmp_path / "timeout" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
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
    assert "039490" not in json.dumps(payload, sort_keys=True)


def test_kiwoom_websocket_smoke_retries_connect_failure_before_login() -> None:
    transport = _FlakyKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            max_messages=3,
            connect_attempts=2,
            connect_backoff_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert result["connection_attempts"] == 2
    assert transport.urls == [
        "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "wss://api.kiwoom.com:10000/api/dostk/websocket",
    ]
    assert transport.sent[0] == {"trnm": "LOGIN", "token": "access-token"}
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_with_evidence_writes_connection_error_summary(tmp_path) -> None:
    transport = _FailingKiwoomWebSocketTransport()
    target = tmp_path / "connection-error" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
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
    assert "039490" not in json.dumps(payload, sort_keys=True)


def test_kiwoom_websocket_smoke_reconnects_and_resubscribes_after_receive_drop() -> None:
    transport = _ReconnectKiwoomWebSocketTransport()

    result = asyncio.run(
        kiwoom.run_websocket_smoke(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            transport=transport,
            max_messages=4,
            reconnect_attempts=1,
            reconnect_backoff_seconds=0,
        )
    )

    first_socket, second_socket = transport.sockets
    assert result["status"] == "ok"
    assert result["reconnects"] == 1
    assert result["connection_attempts"] == 2
    assert result["received_frames"] == 4
    assert transport.urls == [
        "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "wss://api.kiwoom.com:10000/api/dostk/websocket",
    ]
    assert first_socket.sent == second_socket.sent
    assert first_socket.closed is True
    assert second_socket.closed is True


def test_kiwoom_websocket_smoke_with_evidence_writes_reconnect_summary(tmp_path) -> None:
    transport = _ReconnectKiwoomWebSocketTransport()
    target = tmp_path / "reconnect" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            max_messages=4,
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
    assert payload["subscription"] == {"item_count": 1, "types": ["0B"]}
    assert "039490" not in json.dumps(payload, sort_keys=True)
    assert "005930" not in json.dumps(payload, sort_keys=True)


def test_kiwoom_websocket_smoke_records_subscription_ack_summary() -> None:
    transport = _SubscriptionAckKiwoomWebSocketTransport()

    result = asyncio.run(kiwoom.run_websocket_smoke(_kiwoom_ws_cfg(), symbols=["KRX:039490"], transport=transport))

    assert result["status"] == "ok"
    assert result["received_frames"] == 3
    assert result["subscription_events"] == [
        {
            "trnm": "REG",
            "status": "ok",
            "code": "0",
            "message": "SUBSCRIBE SUCCESS",
            "group_no": "1",
            "item_count": 1,
            "types": ["0B"],
        }
    ]
    assert result["sample_payloads"] == [{"trnm": "REAL", "data": [{"item": "039490", "type": "0B"}]}]
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_evidence_redacts_subscription_ack_values() -> None:
    result = {
        "status": "ok",
        "connector": "kiwoom",
        "profile": "paper",
        "network": "injected_transport",
        "uri": "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "login": "ok",
        "subscription": {"items": ["039490"], "types": ["0B"]},
        "subscription_events": [
            {
                "trnm": "REG",
                "status": "ok",
                "code": "0",
                "message": "SUBSCRIBE SUCCESS",
                "group_no": "1",
                "items": ["039490", "005930"],
                "types": ["0B"],
                "token": "secret-token",
            }
        ],
        "received_frames": 1,
        "sample_payloads": [],
    }

    evidence = kiwoom.websocket_smoke_evidence(result)

    assert evidence["subscription_events"] == [
        {
            "trnm": "REG",
            "status": "ok",
            "code": "0",
            "message": "SUBSCRIBE SUCCESS",
            "group_no": "1",
            "item_count": 2,
            "types": ["0B"],
        }
    ]
    dumped = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    assert "039490" not in dumped
    assert "005930" not in dumped
    assert "secret-token" not in dumped


def test_kiwoom_websocket_smoke_fails_on_subscription_error() -> None:
    transport = _SubscriptionErrorKiwoomWebSocketTransport()

    result = asyncio.run(kiwoom.run_websocket_smoke(_kiwoom_ws_cfg(), symbols=["KRX:039490"], transport=transport))

    assert result["status"] == "subscription_error"
    assert result["received_frames"] == 2
    assert result["subscription_events"] == [
        {
            "trnm": "REG",
            "status": "error",
            "code": "900",
            "message": "SUBSCRIBE FAIL",
            "group_no": "1",
            "item_count": 1,
            "types": ["0B"],
        }
    ]
    assert result["sample_payloads"] == []
    assert result["reason"] == "Kiwoom WebSocket subscription failed: SUBSCRIBE FAIL"
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_with_evidence_writes_subscription_error_summary(tmp_path) -> None:
    transport = _SubscriptionErrorKiwoomWebSocketTransport()
    target = tmp_path / "subscription-error" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "subscription_error"
    assert payload["status"] == "subscription_error"
    assert payload["reason"] == "Kiwoom WebSocket subscription failed: SUBSCRIBE FAIL"
    assert payload["subscription_events"] == [
        {
            "trnm": "REG",
            "status": "error",
            "code": "900",
            "message": "SUBSCRIBE FAIL",
            "group_no": "1",
            "item_count": 1,
            "types": ["0B"],
        }
    ]
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "039490" not in dumped


def test_kiwoom_websocket_smoke_fails_on_frame_error() -> None:
    transport = _FrameErrorKiwoomWebSocketTransport()

    result = asyncio.run(kiwoom.run_websocket_smoke(_kiwoom_ws_cfg(), symbols=["KRX:039490"], transport=transport))

    assert result["status"] == "frame_error"
    assert result["received_frames"] == 2
    assert result["frame_errors"] == [{"status": "error", "error": "malformed Kiwoom WebSocket frame"}]
    assert result["sample_payloads"] == []
    assert result["reason"] == "Kiwoom WebSocket smoke received an invalid frame: malformed Kiwoom WebSocket frame"
    assert transport.sent[-1] == {"closed": True}


def test_kiwoom_websocket_smoke_with_evidence_writes_frame_error_summary(tmp_path) -> None:
    transport = _FrameErrorKiwoomWebSocketTransport()
    target = tmp_path / "frame-error" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
        )
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert result["status"] == "frame_error"
    assert payload["status"] == "frame_error"
    assert payload["frame_errors"] == [{"status": "error", "error": "malformed Kiwoom WebSocket frame"}]
    assert payload["reason"] == "Kiwoom WebSocket smoke received an invalid frame: malformed Kiwoom WebSocket frame"
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "039490" not in dumped
    assert "secret-token" not in dumped


def test_kiwoom_websocket_smoke_evidence_redacts_subscription_and_sample_values() -> None:
    result = {
        "status": "ok",
        "connector": "kiwoom",
        "profile": "paper",
        "network": "injected_transport",
        "uri": "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "login": "ok",
        "subscription": {"items": ["039490", "005930"], "types": ["0B"]},
        "received_frames": 2,
        "sample_payloads": [
            {
                "trnm": "REAL",
                "data": [
                    {
                        "item": "039490",
                        "type": "0B",
                        "acct_no": "12345678-01",
                        "price": "70000",
                    }
                ],
                "raw": {
                    "account_number": "12345678",
                    "access_token": "secret-token",
                },
            }
        ],
    }

    evidence = kiwoom.websocket_smoke_evidence(result)

    assert evidence["subscription"] == {
        "item_count": 2,
        "types": ["0B"],
    }
    assert evidence["sample_count"] == 1
    sample = evidence["sample_payloads"][0]
    assert sample["trnm"] == "REAL"
    assert sample["data_count"] == 1
    assert sample["data_keys"] == ["acct_no", "item", "price", "type"]
    assert sample["raw_keys"] == ["access_token", "account_number"]
    assert "data" not in sample
    assert "raw" not in sample
    serialized = json.dumps(evidence, sort_keys=True)
    assert "039490" not in serialized
    assert "005930" not in serialized
    assert "12345678" not in serialized
    assert "secret-token" not in serialized


def test_kiwoom_write_websocket_smoke_evidence_saves_redacted_json(tmp_path) -> None:
    result = {
        "status": "ok",
        "connector": "kiwoom",
        "profile": "paper",
        "network": "injected_transport",
        "uri": "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "login": "ok",
        "subscription": {"items": ["039490", "005930"], "types": ["0B"]},
        "received_frames": 2,
        "sample_payloads": [
            {
                "trnm": "REAL",
                "data": [
                    {
                        "item": "039490",
                        "type": "0B",
                        "acct_no": "12345678-01",
                        "price": "70000",
                    }
                ],
                "raw": {
                    "account_number": "12345678",
                    "access_token": "secret-token",
                },
            }
        ],
    }
    target = tmp_path / "nested" / "kiwoom-websocket-smoke.json"

    written = kiwoom.write_websocket_smoke_evidence(result, target)

    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["subscription"] == {
        "item_count": 2,
        "types": ["0B"],
    }
    assert payload["sample_payloads"][0]["data_keys"] == ["acct_no", "item", "price", "type"]
    assert payload["sample_payloads"][0]["raw_keys"] == ["access_token", "account_number"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "039490" not in serialized
    assert "005930" not in serialized
    assert "12345678" not in serialized
    assert "secret-token" not in serialized
    assert "data" not in payload["sample_payloads"][0]
    assert "raw" not in payload["sample_payloads"][0]


def test_kiwoom_websocket_smoke_with_evidence_requires_broker_call_opt_in(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["039490"],
            evidence_path=target,
            transport=transport,
        )
    )

    assert result["status"] == "not_run"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert "allow_broker_calls=True" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []
    assert not target.exists()


def test_kiwoom_websocket_smoke_with_evidence_blocks_live_without_live_opt_in(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "kiwoom-websocket-smoke-live.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(profile="live"),
            symbols=["039490"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
        )
    )

    assert result["status"] == "blocked"
    assert result["environment"] == "live"
    assert result["network"] == "not_attempted"
    assert result["evidence_path"] is None
    assert "allow_live=True" in result["reason"]
    assert transport.uri == ""
    assert transport.sent == []
    assert not target.exists()


def test_kiwoom_websocket_smoke_with_evidence_writes_only_redacted_summary(tmp_path) -> None:
    transport = _FakeKiwoomWebSocketTransport()
    target = tmp_path / "nested" / "kiwoom-websocket-smoke.json"

    result = asyncio.run(
        kiwoom.run_websocket_smoke_with_evidence(
            _kiwoom_ws_cfg(),
            symbols=["KRX:039490", "005930.KS"],
            evidence_path=target,
            transport=transport,
            allow_broker_calls=True,
            max_messages=3,
        )
    )

    assert result["status"] == "ok"
    assert result["evidence_path"] == str(target)
    assert result["subscription"] == {
        "item_count": 2,
        "types": ["0B"],
    }
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {key: value for key, value in result.items() if key != "evidence_path"}
    serialized = json.dumps(result, sort_keys=True)
    assert "039490" not in serialized
    assert "005930" not in serialized
    assert "access-token" not in serialized
    assert "app-secret" not in serialized
    assert transport.uri == "wss://api.kiwoom.com:10000/api/dostk/websocket"
