"""Kiwoom official REST WebSocket contract tests.

These tests pin only the WebSocket URL and JSON frames shown in Kiwoom's
official REST API "Web Socket" guide. They do not open a real socket or require
live credentials.
"""

from __future__ import annotations

import pytest

from src.trading.connectors.kiwoom import sdk as kiwoom

pytestmark = pytest.mark.unit


def test_kiwoom_websocket_catalog_matches_official_realtime_sample() -> None:
    endpoint = kiwoom.KIWOOM_WEBSOCKET_ENDPOINTS["domestic_stock_realtime"]

    assert endpoint["url"] == "wss://api.kiwoom.com:10000/api/dostk/websocket"
    assert endpoint["login_trnm"] == "LOGIN"
    assert endpoint["subscribe_trnm"] == "REG"
    assert endpoint["ping_trnm"] == "PING"
    assert endpoint["sample_type"] == "0B"


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
