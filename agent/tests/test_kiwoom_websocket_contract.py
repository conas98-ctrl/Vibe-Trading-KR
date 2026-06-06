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
