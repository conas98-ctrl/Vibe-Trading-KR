"""Kiwoom REST OpenAPI connector.

The endpoint catalog is derived from Kiwoom's official OpenAPI guide pages.
Only verified REST contracts are exposed; anything outside this catalog stays
fail-closed until its official request/response surface is pinned by tests.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from src.config.paths import get_runtime_root
from src.tools.redaction import redact_payload
from src.trading.connectors.kr_common import (
    KoreanConnectorConfig,
    KoreanConnectorConfigError,
    build_config as _build_config,
    check_status as _check_status,
    load_config as _load_config,
    save_config as _save_config,
)

CONFIG_FILENAME = "kiwoom.json"
PAPER_URL = "https://mockapi.kiwoom.com"
LIVE_URL = "https://api.kiwoom.com"
LABEL = "Kiwoom REST OpenAPI"
CONNECTOR = "kiwoom"

KIWOOM_REST_ENDPOINTS: dict[str, dict[str, str]] = {
    "auth_token": {
        "method": "POST",
        "path": "/oauth2/token",
        "content_type": "application/json;charset=UTF-8",
    },
    "stock_info": {
        "method": "POST",
        "path": "/api/dostk/stkinfo",
        "api_id": "ka10001",
    },
    "daily_chart": {
        "method": "POST",
        "path": "/api/dostk/chart",
        "api_id": "ka10081",
    },
    "account_balance": {
        "method": "POST",
        "path": "/api/dostk/acnt",
        "api_id": "kt00018",
    },
    "open_orders": {
        "method": "POST",
        "path": "/api/dostk/acnt",
        "api_id": "ka10075",
    },
    "stock_buy_order": {
        "method": "POST",
        "path": "/api/dostk/ordr",
        "api_id": "kt10000",
    },
    "stock_sell_order": {
        "method": "POST",
        "path": "/api/dostk/ordr",
        "api_id": "kt10001",
    },
    "stock_modify_order": {
        "method": "POST",
        "path": "/api/dostk/ordr",
        "api_id": "kt10002",
    },
    "stock_cancel_order": {
        "method": "POST",
        "path": "/api/dostk/ordr",
        "api_id": "kt10003",
    },
}

KIWOOM_WEBSOCKET_ENDPOINTS: dict[str, dict[str, str]] = {
    "domestic_stock_realtime": {
        "url": "wss://api.kiwoom.com:10000/api/dostk/websocket",
        "login_trnm": "LOGIN",
        "subscribe_trnm": "REG",
        "ping_trnm": "PING",
        "sample_type": "0B",
    },
}

KIWOOM_WEBSOCKET_CONDITION_TRS: dict[str, dict[str, str]] = {
    "condition_list": {
        "api_id": "ka10171",
        "trnm": "CNSRLST",
        "description": "조건검색 목록조회",
    },
}


KIWOOM_WEBSOCKET_CONDITION_REQUEST_TRS: dict[str, dict[str, str]] = {
    "general": {
        "api_id": "ka10172",
        "trnm": "CNSRREQ",
        "search_type": "0",
        "stex_tp": "K",
        "description": "조건검색 요청 일반",
    },
}


KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS: dict[str, dict[str, str]] = {
    "subscribe": {
        "api_id": "ka10173",
        "trnm": "CNSRREQ",
        "search_type": "1",
        "stex_tp": "K",
        "realtime_trnm": "REAL",
        "description": "조건검색 요청 실시간",
    },
}


KIWOOM_WEBSOCKET_CONDITION_UNSUBSCRIBE_TRS: dict[str, dict[str, str]] = {
    "unsubscribe": {
        "api_id": "ka10174",
        "method": "POST",
        "path": "/api/dostk/websocket",
        "trnm": "CNSRCLR",
        "description": "조건검색 실시간 해제",
    },
}

KIWOOM_WEBSOCKET_REALTIME_TYPES: dict[str, str] = {
    "00": "주문체결",
    "04": "잔고",
    "0A": "주식기세",
    "0B": "주식체결",
    "0C": "주식우선호가",
    "0D": "주식호가잔량",
    "0E": "주식시간외호가",
    "0F": "주식당일거래원",
    "0G": "ETF NAV",
    "0H": "주식예상체결",
    "0I": "국제금환산가격",
    "0J": "업종지수",
    "0U": "업종등락",
    "0g": "주식종목정보",
    "0m": "ELW 이론가",
    "0s": "장시작시간",
    "0u": "ELW 지표",
    "0w": "종목프로그램매매",
    "1h": "VI발동/해제",
}

KIWOOM_WEBSOCKET_ORDERBOOK_FIELDS: dict[str, str] = {
    "21": "호가시간",
    "41": "매도호가1",
    "61": "매도호가수량1",
    "81": "매도호가직전대비1",
    "51": "매수호가1",
    "71": "매수호가수량1",
    "91": "매수호가직전대비1",
    "42": "매도호가2",
    "62": "매도호가수량2",
    "82": "매도호가직전대비2",
    "52": "매수호가2",
    "72": "매수호가수량2",
    "92": "매수호가직전대비2",
    "43": "매도호가3",
    "63": "매도호가수량3",
    "83": "매도호가직전대비3",
    "53": "매수호가3",
    "73": "매수호가수량3",
    "93": "매수호가직전대비3",
    "44": "매도호가4",
    "64": "매도호가수량4",
    "84": "매도호가직전대비4",
    "54": "매수호가4",
    "74": "매수호가수량4",
    "94": "매수호가직전대비4",
    "45": "매도호가5",
    "65": "매도호가수량5",
    "85": "매도호가직전대비5",
    "55": "매수호가5",
    "75": "매수호가수량5",
    "95": "매수호가직전대비5",
    "46": "매도호가6",
    "66": "매도호가수량6",
    "86": "매도호가직전대비6",
    "56": "매수호가6",
    "76": "매수호가수량6",
    "96": "매수호가직전대비6",
    "47": "매도호가7",
    "67": "매도호가수량7",
    "87": "매도호가직전대비7",
    "57": "매수호가7",
    "77": "매수호가수량7",
    "97": "매수호가직전대비7",
    "48": "매도호가8",
    "68": "매도호가수량8",
    "88": "매도호가직전대비8",
    "58": "매수호가8",
    "78": "매수호가수량8",
    "98": "매수호가직전대비8",
    "49": "매도호가9",
    "69": "매도호가수량9",
    "89": "매도호가직전대비9",
    "59": "매수호가9",
    "79": "매수호가수량9",
    "99": "매수호가직전대비9",
    "50": "매도호가10",
    "70": "매도호가수량10",
    "60": "매수호가10",
    "90": "매도호가직전대비10",
    "80": "매수호가수량10",
    "100": "매수호가직전대비10",
    "121": "매도호가총잔량",
    "122": "매도호가총잔량직전대비",
    "125": "매수호가총잔량",
    "126": "매수호가총잔량직전대비",
    "23": "예상체결가",
    "24": "예상체결수량",
    "128": "순매수잔량",
    "129": "매수비율",
    "138": "순매도잔량",
    "139": "매도비율",
    "200": "예상체결가전일종가대비",
    "201": "예상체결가전일종가대비등락율",
    "238": "예상체결가전일종가대비기호",
    "291": "예상체결가",
    "292": "예상체결량",
    "293": "예상체결가전일대비기호",
    "294": "예상체결가전일대비",
    "295": "예상체결가전일대비등락율",
    "621": "LP매도호가수량1",
    "631": "LP매수호가수량1",
    "622": "LP매도호가수량2",
    "632": "LP매수호가수량2",
    "623": "LP매도호가수량3",
    "633": "LP매수호가수량3",
    "624": "LP매도호가수량4",
    "634": "LP매수호가수량4",
    "625": "LP매도호가수량5",
    "635": "LP매수호가수량5",
    "626": "LP매도호가수량6",
    "636": "LP매수호가수량6",
    "627": "LP매도호가수량7",
    "637": "LP매수호가수량7",
    "628": "LP매도호가수량8",
    "638": "LP매수호가수량8",
    "629": "LP매도호가수량9",
    "639": "LP매수호가수량9",
    "630": "LP매도호가수량10",
    "640": "LP매수호가수량10",
    "13": "누적거래량",
    "299": "전일거래량대비예상체결율",
    "215": "장운영구분",
    "216": "투자자별ticker",
    "6044": "KRX 매도호가잔량1",
    "6045": "KRX 매도호가잔량2",
    "6046": "KRX 매도호가잔량3",
    "6047": "KRX 매도호가잔량4",
    "6048": "KRX 매도호가잔량5",
    "6049": "KRX 매도호가잔량6",
    "6050": "KRX 매도호가잔량7",
    "6051": "KRX 매도호가잔량8",
    "6052": "KRX 매도호가잔량9",
    "6053": "KRX 매도호가잔량10",
    "6054": "KRX 매수호가잔량1",
    "6055": "KRX 매수호가잔량2",
    "6056": "KRX 매수호가잔량3",
    "6057": "KRX 매수호가잔량4",
    "6058": "KRX 매수호가잔량5",
    "6059": "KRX 매수호가잔량6",
    "6060": "KRX 매수호가잔량7",
    "6061": "KRX 매수호가잔량8",
    "6062": "KRX 매수호가잔량9",
    "6063": "KRX 매수호가잔량10",
    "6064": "KRX 매도호가총잔량",
    "6065": "KRX 매수호가총잔량",
    "6066": "NXT 매도호가잔량1",
    "6067": "NXT 매도호가잔량2",
    "6068": "NXT 매도호가잔량3",
    "6069": "NXT 매도호가잔량4",
    "6070": "NXT 매도호가잔량5",
    "6071": "NXT 매도호가잔량6",
    "6072": "NXT 매도호가잔량7",
    "6073": "NXT 매도호가잔량8",
    "6074": "NXT 매도호가잔량9",
    "6075": "NXT 매도호가잔량10",
    "6076": "NXT 매수호가잔량1",
    "6077": "NXT 매수호가잔량2",
    "6078": "NXT 매수호가잔량3",
    "6079": "NXT 매수호가잔량4",
    "6080": "NXT 매수호가잔량5",
    "6081": "NXT 매수호가잔량6",
    "6082": "NXT 매수호가잔량7",
    "6083": "NXT 매수호가잔량8",
    "6084": "NXT 매수호가잔량9",
    "6085": "NXT 매수호가잔량10",
    "6086": "NXT 매도호가총잔량",
    "6087": "NXT 매수호가총잔량",
    "6100": "KRX 중간가 매도 총잔량 증감",
    "6101": "KRX 중간가 매도 총잔량",
    "6102": "KRX 중간가",
    "6103": "KRX 중간가 매수 총잔량",
    "6104": "KRX 중간가 매수 총잔량 증감",
    "6105": "NXT중간가 매도 총잔량 증감",
    "6106": "NXT중간가 매도 총잔량",
    "6107": "NXT중간가",
    "6108": "NXT중간가 매수 총잔량",
    "6109": "NXT중간가 매수 총잔량 증감",
    "6110": "KRX중간가대비",
    "6111": "KRX중간가대비 기호",
    "6112": "KRX중간가대비등락율",
    "6113": "NXT중간가대비",
    "6114": "NXT중간가대비 기호",
    "6115": "NXT중간가대비등락율",
}


KIWOOM_WEBSOCKET_TRADE_FIELDS: dict[str, str] = {
    "20": "체결시간",
    "10": "현재가",
    "11": "전일대비",
    "12": "등락율",
    "27": "(최우선)매도호가",
    "28": "(최우선)매수호가",
    "15": "거래량",
    "13": "누적거래량",
    "14": "누적거래대금",
    "16": "시가",
    "17": "고가",
    "18": "저가",
    "25": "전일대비기호",
    "26": "전일거래량대비(계약,주)",
    "29": "거래대금증감",
    "30": "전일거래량대비(비율)",
    "31": "거래회전율",
    "32": "거래비용",
    "228": "체결강도",
    "311": "시가총액(억)",
    "290": "장구분",
    "691": "K.O 접근도",
    "567": "상한가발생시간",
    "568": "하한가발생시간",
    "851": "전일 동시간 거래량 비율",
    "1890": "시가시간",
    "1891": "고가시간",
    "1892": "저가시간",
    "1030": "매도체결량",
    "1031": "매수체결량",
    "1032": "매수비율",
    "1071": "매도체결건수",
    "1072": "매수체결건수",
    "1313": "순간거래대금",
    "1315": "매도체결량_단건",
    "1316": "매수체결량_단건",
    "1314": "순매수체결량",
    "1497": "CFD증거금",
    "1498": "유지증거금",
    "620": "당일거래평균가",
    "732": "CFD거래비용",
    "852": "대주거래비용",
    "9081": "거래소구분",
}


KIWOOM_WEBSOCKET_BEST_QUOTE_FIELDS: dict[str, str] = {
    "27": "(최우선)매도호가",
    "28": "(최우선)매수호가",
}


def config_path() -> Path:
    return get_runtime_root() / CONFIG_FILENAME


def load_config() -> KoreanConnectorConfig:
    return _load_config(config_path(), connector=CONNECTOR, paper_url=PAPER_URL, live_url=LIVE_URL)


def save_config(config: KoreanConnectorConfig) -> Path:
    return _save_config(config_path(), config)


def build_config(profile_config: Mapping[str, Any] | None = None, overrides: Mapping[str, Any] | None = None) -> KoreanConnectorConfig:
    return _build_config(
        config_path=config_path(),
        connector=CONNECTOR,
        profile_config=profile_config,
        overrides=overrides,
        paper_url=PAPER_URL,
        live_url=LIVE_URL,
    )


def check_status(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    report = _check_status(config or load_config(), label=LABEL)
    report["auth_probe"] = "not_run"
    report["auth_probe_reason"] = "Kiwoom token issuance is deferred until an explicit read/order call."
    realtime_types = ",".join(KIWOOM_WEBSOCKET_REALTIME_TYPES)
    condition_apis = ",".join(
        f"websocket:{spec['api_id']}"
        for catalog in (
            KIWOOM_WEBSOCKET_CONDITION_TRS,
            KIWOOM_WEBSOCKET_CONDITION_REQUEST_TRS,
            KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS,
            KIWOOM_WEBSOCKET_CONDITION_UNSUBSCRIBE_TRS,
        )
        for spec in catalog.values()
    )
    report["official_catalog"] = (
        "ka10001,ka10081,kt00018,ka10075,kt10000,kt10001,kt10002,kt10003,"
        f"websocket:{realtime_types},{condition_apis}"
    )
    return report


def build_websocket_login_frame(access_token: str) -> dict[str, str]:
    token = str(access_token or "").strip()
    if not token:
        raise KoreanConnectorConfigError("Kiwoom WebSocket login frame requires access token.")
    return {"trnm": KIWOOM_WEBSOCKET_ENDPOINTS["domestic_stock_realtime"]["login_trnm"], "token": token}


def build_websocket_subscribe_frame(
    symbols: list[str] | tuple[str, ...],
    *,
    group_no: int | str = 1,
    channel: str = "domestic_stock_realtime",
    refresh: bool = True,
    types: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    endpoint = KIWOOM_WEBSOCKET_ENDPOINTS.get(channel)
    if endpoint is None:
        raise KoreanConnectorConfigError(f"Unknown Kiwoom WebSocket channel: {channel}.")
    items = [_normalize_kr_symbol(symbol) for symbol in symbols if str(symbol or "").strip()]
    if not items:
        raise KoreanConnectorConfigError("Kiwoom WebSocket subscribe frame requires at least one symbol.")
    type_codes = [str(code).strip() for code in (types or (endpoint["sample_type"],)) if str(code).strip()]
    if not type_codes:
        raise KoreanConnectorConfigError("Kiwoom WebSocket subscribe frame requires at least one type code.")
    unknown = [code for code in type_codes if code not in KIWOOM_WEBSOCKET_REALTIME_TYPES]
    if unknown:
        raise KoreanConnectorConfigError(f"Unknown Kiwoom WebSocket realtime type: {', '.join(unknown)}.")
    return {
        "trnm": endpoint["subscribe_trnm"],
        "grp_no": str(group_no),
        "refresh": "1" if refresh else "0",
        "data": [{"item": items, "type": type_codes}],
    }


def build_websocket_condition_list_frame() -> dict[str, str]:
    return {"trnm": KIWOOM_WEBSOCKET_CONDITION_TRS["condition_list"]["trnm"]}


def parse_websocket_condition_list(message: Mapping[str, Any]) -> list[dict[str, str]]:
    expected_trnm = KIWOOM_WEBSOCKET_CONDITION_TRS["condition_list"]["trnm"]
    trnm = str(message.get("trnm") or "").strip()
    if trnm != expected_trnm:
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition list expected {expected_trnm}, got {trnm or 'missing'}.")
    if str(message.get("return_code", 0)).strip() not in {"0", ""}:
        reason = str(message.get("return_msg") or "unknown error").strip()
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition list failed: {reason}.")

    conditions: list[dict[str, str]] = []
    data = message.get("data")
    rows = data if isinstance(data, list) else [data] if isinstance(data, Mapping) else []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            conditions.append({"seq": str(row[0]).strip(), "name": str(row[1]).strip()})
        elif isinstance(row, Mapping):
            conditions.append({"seq": str(row.get("seq") or "").strip(), "name": str(row.get("name") or "").strip()})
    return conditions


def build_websocket_condition_request_frame(
    seq: int | str,
    *,
    cont_yn: str = "N",
    next_key: str = "",
    exchange: str = "K",
) -> dict[str, str]:
    request = KIWOOM_WEBSOCKET_CONDITION_REQUEST_TRS["general"]
    clean_seq = str(seq or "").strip()
    if not clean_seq:
        raise KoreanConnectorConfigError("Kiwoom WebSocket condition request frame requires condition sequence.")
    clean_exchange = str(exchange or "").strip().upper()
    if clean_exchange != request["stex_tp"]:
        raise KoreanConnectorConfigError("Kiwoom WebSocket condition request only pins KRX exchange `K`.")
    clean_cont_yn = str(cont_yn or "N").strip().upper()
    if clean_cont_yn not in {"Y", "N"}:
        raise KoreanConnectorConfigError("Kiwoom WebSocket condition request cont_yn must be `Y` or `N`.")
    return {
        "trnm": request["trnm"],
        "seq": clean_seq,
        "search_type": request["search_type"],
        "stex_tp": request["stex_tp"],
        "cont_yn": clean_cont_yn,
        "next_key": str(next_key or "").strip(),
    }


def parse_websocket_condition_request_response(message: Mapping[str, Any]) -> dict[str, Any]:
    expected_trnm = KIWOOM_WEBSOCKET_CONDITION_REQUEST_TRS["general"]["trnm"]
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != expected_trnm:
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition request expected {expected_trnm}, got {trnm or 'missing'}.")
    if str(message.get("return_code", "0")).strip() not in {"0", ""}:
        reason = str(message.get("return_msg") or "unknown error").strip()
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition request failed: {reason}.")
    return {
        "seq": str(message.get("seq") or "").strip(),
        "cont_yn": str(message.get("cont_yn") or "").strip(),
        "next_key": str(message.get("next_key") or "").strip(),
        "results": [_condition_result_to_dict(item) for item in _as_list(message.get("data"))],
        "raw": dict(message),
    }


def build_websocket_condition_realtime_frame(seq: int | str, *, exchange: str = "K") -> dict[str, str]:
    request = KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS["subscribe"]
    clean_seq = str(seq or "").strip()
    if not clean_seq:
        raise KoreanConnectorConfigError("Kiwoom WebSocket condition realtime frame requires condition sequence.")
    clean_exchange = str(exchange or "").strip().upper()
    if clean_exchange != request["stex_tp"]:
        raise KoreanConnectorConfigError("Kiwoom WebSocket condition realtime request only pins KRX exchange `K`.")
    return {
        "trnm": request["trnm"],
        "seq": clean_seq,
        "search_type": request["search_type"],
        "stex_tp": request["stex_tp"],
    }


def parse_websocket_condition_realtime_response(message: Mapping[str, Any]) -> dict[str, Any]:
    expected_trnm = KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS["subscribe"]["trnm"]
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != expected_trnm:
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition realtime request expected {expected_trnm}, got {trnm or 'missing'}.")
    if str(message.get("return_code", "0")).strip() not in {"0", ""}:
        reason = str(message.get("return_msg") or "unknown error").strip()
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition realtime request failed: {reason}.")
    raw_symbols = [str(item.get("jmcode") or "").strip() for item in _as_list(message.get("data")) if str(item.get("jmcode") or "").strip()]
    return {
        "seq": str(message.get("seq") or "").strip(),
        "symbols": [_normalize_position_symbol(symbol) for symbol in raw_symbols],
        "raw_symbols": raw_symbols,
        "raw": dict(message),
    }


def parse_websocket_condition_realtime_message(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_trnm = KIWOOM_WEBSOCKET_CONDITION_REALTIME_TRS["subscribe"]["realtime_trnm"]
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != expected_trnm:
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket condition realtime message expected {expected_trnm}, got {trnm or 'missing'}.")
    return [_condition_realtime_to_dict(item) for item in _as_list(message.get("data"))]


def build_websocket_condition_unsubscribe_frame(seq: str | int) -> dict[str, str]:
    condition_seq = str(seq or "").strip()
    if not condition_seq:
        raise KoreanConnectorConfigError("Kiwoom condition unsubscribe frame requires condition sequence.")
    return {"trnm": KIWOOM_WEBSOCKET_CONDITION_UNSUBSCRIBE_TRS["unsubscribe"]["trnm"], "seq": condition_seq}


def parse_websocket_condition_unsubscribe_response(message: Mapping[str, Any]) -> dict[str, Any]:
    expected_trnm = KIWOOM_WEBSOCKET_CONDITION_UNSUBSCRIBE_TRS["unsubscribe"]["trnm"]
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != expected_trnm:
        raise KoreanConnectorConfigError(f"unexpected Kiwoom condition unsubscribe TR: {trnm or 'missing'}.")
    if str(message.get("return_code", "")).strip() != "0":
        reason = str(message.get("return_msg") or "unknown error").strip()
        raise KoreanConnectorConfigError(f"Kiwoom condition unsubscribe failed: {reason}")
    seq = str(message.get("seq") or "").strip()
    if not seq:
        raise KoreanConnectorConfigError("Kiwoom condition unsubscribe response requires condition sequence.")
    return {"status": "ok", "seq": seq, "raw": dict(message)}


def websocket_control_reply(message: Mapping[str, Any]) -> dict[str, Any] | None:
    endpoint = KIWOOM_WEBSOCKET_ENDPOINTS["domestic_stock_realtime"]
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm == endpoint["ping_trnm"]:
        return dict(message)
    if trnm == endpoint["login_trnm"] and str(message.get("return_code", "0")).strip() not in {"0", ""}:
        reason = str(message.get("return_msg") or "unknown error").strip()
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket login failed: {reason}")
    return None


def parse_websocket_orderbook_snapshots(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != "REAL":
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket orderbook parser expected REAL, got {trnm or 'missing'}.")

    data = message.get("data")
    if isinstance(data, Mapping):
        rows = [dict(data)]
    elif isinstance(data, list):
        if any(not isinstance(item, Mapping) for item in data):
            raise KoreanConnectorConfigError("Kiwoom WebSocket orderbook requires data mappings.")
        rows = [dict(item) for item in data]
    else:
        raise KoreanConnectorConfigError("Kiwoom WebSocket orderbook requires data mapping or list.")

    snapshots = []
    for item in rows:
        real_type = str(item.get("type") or "").strip()
        if real_type != "0D":
            raise KoreanConnectorConfigError(f"Kiwoom WebSocket orderbook parser expected type 0D, got {real_type or 'missing'}.")
        values = item.get("values")
        if not isinstance(values, Mapping):
            raise KoreanConnectorConfigError("Kiwoom WebSocket orderbook requires values mapping.")
        raw_values = {str(key): value for key, value in values.items()}
        snapshots.append(
            {
                "type": real_type,
                "name": str(item.get("name") or KIWOOM_WEBSOCKET_REALTIME_TYPES["0D"]).strip(),
                "symbol": _normalize_position_symbol(item.get("item")),
                "time": str(raw_values.get("21") or "").strip(),
                "asks": [_orderbook_level(raw_values, level, side="ask") for level in range(1, 11)],
                "bids": [_orderbook_level(raw_values, level, side="bid") for level in range(1, 11)],
                "total_ask_quantity": _to_float(raw_values.get("121")),
                "total_ask_change": _to_float(raw_values.get("122")),
                "total_bid_quantity": _to_float(raw_values.get("125")),
                "total_bid_change": _to_float(raw_values.get("126")),
                "expected_price": _to_abs_float(raw_values.get("23")),
                "expected_quantity": _to_float(raw_values.get("24")),
                "net_bid_quantity": _to_float(raw_values.get("128")),
                "bid_ratio": _to_float(raw_values.get("129")),
                "net_ask_quantity": _to_float(raw_values.get("138")),
                "ask_ratio": _to_float(raw_values.get("139")),
                "expected_close_change": _to_float(raw_values.get("200")),
                "expected_close_change_rate": _to_float(raw_values.get("201")),
                "expected_close_change_sign": str(raw_values.get("238") or "").strip(),
                "preopen_expected_price": _to_abs_float(raw_values.get("291")),
                "preopen_expected_quantity": _to_float(raw_values.get("292")),
                "preopen_change_sign": str(raw_values.get("293") or "").strip(),
                "preopen_change": _to_float(raw_values.get("294")),
                "preopen_change_rate": _to_float(raw_values.get("295")),
                "cumulative_volume": _to_float(raw_values.get("13")),
                "expected_volume_rate": _to_float(raw_values.get("299")),
                "session_code": str(raw_values.get("215") or "").strip(),
                "investor_ticker": str(raw_values.get("216") or "").strip(),
                "krx_total_ask_quantity": _to_float(raw_values.get("6064")),
                "krx_total_bid_quantity": _to_float(raw_values.get("6065")),
                "nxt_total_ask_quantity": _to_float(raw_values.get("6086")),
                "nxt_total_bid_quantity": _to_float(raw_values.get("6087")),
                "krx_mid_price": _to_abs_float(raw_values.get("6102")),
                "nxt_mid_price": _to_abs_float(raw_values.get("6107")),
                "raw_values": raw_values,
                "raw": dict(item),
            }
        )
    return snapshots


def parse_websocket_trade_ticks(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != "REAL":
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket trade tick parser expected REAL, got {trnm or 'missing'}.")

    data = message.get("data")
    if isinstance(data, Mapping):
        rows = [dict(data)]
    elif isinstance(data, list):
        if any(not isinstance(item, Mapping) for item in data):
            raise KoreanConnectorConfigError("Kiwoom WebSocket trade tick requires data mappings.")
        rows = [dict(item) for item in data]
    else:
        raise KoreanConnectorConfigError("Kiwoom WebSocket trade tick requires data mapping or list.")

    ticks = []
    for item in rows:
        real_type = str(item.get("type") or "").strip()
        if real_type != "0B":
            raise KoreanConnectorConfigError(f"Kiwoom WebSocket trade tick parser expected type 0B, got {real_type or 'missing'}.")
        values = item.get("values")
        if not isinstance(values, Mapping):
            raise KoreanConnectorConfigError("Kiwoom WebSocket trade tick requires values mapping.")
        raw_values = {str(key): value for key, value in values.items()}
        signed_volume = _to_float(raw_values.get("15"))
        ticks.append(
            {
                "type": real_type,
                "name": str(item.get("name") or KIWOOM_WEBSOCKET_REALTIME_TYPES["0B"]).strip(),
                "symbol": _normalize_position_symbol(item.get("item")),
                "time": str(raw_values.get("20") or "").strip(),
                "last": _to_abs_float(raw_values.get("10")),
                "change": _to_float(raw_values.get("11")),
                "change_rate": _to_float(raw_values.get("12")),
                "best_ask": _to_abs_float(raw_values.get("27")),
                "best_bid": _to_abs_float(raw_values.get("28")),
                "trade_volume": abs(signed_volume) if signed_volume is not None else None,
                "signed_trade_volume": signed_volume,
                "trade_side": _signed_volume_side(raw_values.get("15")),
                "cumulative_volume": _to_float(raw_values.get("13")),
                "cumulative_value_million_krw": _to_float(raw_values.get("14")),
                "open": _to_abs_float(raw_values.get("16")),
                "high": _to_abs_float(raw_values.get("17")),
                "low": _to_abs_float(raw_values.get("18")),
                "change_sign": str(raw_values.get("25") or "").strip(),
                "trade_strength": _to_float(raw_values.get("228")),
                "market_cap_100m_krw": _to_float(raw_values.get("311")),
                "session_code": str(raw_values.get("290") or "").strip(),
                "exchange_code": str(raw_values.get("9081") or "").strip(),
                "raw_values": raw_values,
                "raw": dict(item),
            }
        )
    return ticks


def parse_websocket_best_quotes(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    trnm = str(message.get("trnm") or "").strip().upper()
    if trnm != "REAL":
        raise KoreanConnectorConfigError(f"Kiwoom WebSocket best quote parser expected REAL, got {trnm or 'missing'}.")

    data = message.get("data")
    if isinstance(data, Mapping):
        rows = [dict(data)]
    elif isinstance(data, list):
        if any(not isinstance(item, Mapping) for item in data):
            raise KoreanConnectorConfigError("Kiwoom WebSocket best quote requires data mappings.")
        rows = [dict(item) for item in data]
    else:
        raise KoreanConnectorConfigError("Kiwoom WebSocket best quote requires data mapping or list.")

    quotes = []
    for item in rows:
        real_type = str(item.get("type") or "").strip()
        if real_type != "0C":
            raise KoreanConnectorConfigError(f"Kiwoom WebSocket best quote parser expected type 0C, got {real_type or 'missing'}.")
        values = item.get("values")
        if not isinstance(values, Mapping):
            raise KoreanConnectorConfigError("Kiwoom WebSocket best quote requires values mapping.")
        raw_values = {str(key): value for key, value in values.items()}
        quotes.append(
            {
                "type": real_type,
                "name": str(item.get("name") or KIWOOM_WEBSOCKET_REALTIME_TYPES["0C"]).strip(),
                "symbol": _normalize_position_symbol(item.get("item")),
                "best_ask": _to_abs_float(raw_values.get("27")),
                "best_bid": _to_abs_float(raw_values.get("28")),
                "raw_values": raw_values,
                "raw": dict(item),
            }
        )
    return quotes
class KiwoomWebSocketConnection:
    """Small adapter around a real Kiwoom WebSocket client connection."""

    def __init__(self, socket: Any, manager: Any | None = None):
        self._socket = socket
        self._manager = manager

    async def send_json(self, payload: Mapping[str, Any]) -> None:
        await self._socket.send(json.dumps(dict(payload), ensure_ascii=False))

    async def receive_json(self) -> dict[str, Any]:
        payload = await self._socket.recv()
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError, ValueError) as exc:
            return {"type": "error", "status": "error", "error": str(exc) or exc.__class__.__name__}
        if not isinstance(data, Mapping):
            return {"type": "error", "status": "error", "error": "Kiwoom WebSocket frame must be a JSON object."}
        return dict(data or {})

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
            return
        await self._socket.close()


class KiwoomWebSocketTransport:
    """Connect to Kiwoom's official WebSocket endpoint using ``websockets``."""

    def __init__(self, connect_factory: Any | None = None):
        self._connect_factory = connect_factory or _websockets_connect

    async def connect(self, url: str) -> KiwoomWebSocketConnection:
        connection = self._connect_factory(url)
        if hasattr(connection, "__await__"):
            return KiwoomWebSocketConnection(await connection)
        if hasattr(connection, "__aenter__"):
            return KiwoomWebSocketConnection(await connection.__aenter__(), manager=connection)
        return KiwoomWebSocketConnection(connection)


def create_websocket_transport() -> KiwoomWebSocketTransport:
    """Return the default Kiwoom WebSocket transport."""

    return KiwoomWebSocketTransport()


async def run_websocket_smoke(
    config: KoreanConnectorConfig | None = None,
    *,
    channel: str = "domestic_stock_realtime",
    symbols: list[str] | tuple[str, ...],
    transport: Any | None = None,
    max_messages: int = 3,
    message_timeout: float | None = None,
    connect_attempts: int = 1,
    connect_backoff_seconds: float = 0.0,
    reconnect_attempts: int = 0,
    reconnect_backoff_seconds: float = 0.0,
) -> dict[str, Any]:
    cfg = config or load_config()
    injected_transport = transport is not None
    if not cfg.access_token:
        return {
            "status": "not_configured",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "missing": ["access_token"],
            "network": "not_attempted",
        }
    try:
        message_target = int(max_messages)
    except (TypeError, ValueError):
        message_target = 0
    if message_target < 1:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "max_messages",
            "requested_value": max_messages,
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "Kiwoom WebSocket smoke max_messages must be a positive integer.",
        }
    timeout_seconds: float | None = None
    if message_timeout is not None:
        try:
            timeout_seconds = float(message_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 0.0
        if timeout_seconds <= 0:
            return {
                "status": "invalid_request",
                "connector": CONNECTOR,
                "profile": cfg.profile,
                "environment": cfg.environment,
                "network": "not_attempted",
                "parameter": "message_timeout",
                "requested_value": message_timeout,
                "received_frames": 0,
                "sample_payloads": [],
                "subscription_events": [],
                "frame_errors": [],
                "reason": "Kiwoom WebSocket smoke message_timeout must be a positive number.",
            }
    try:
        connect_attempt_count = int(connect_attempts)
    except (TypeError, ValueError):
        connect_attempt_count = 0
    if connect_attempt_count < 1:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "connect_attempts",
            "requested_value": connect_attempts,
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "Kiwoom WebSocket smoke connect_attempts must be a positive integer.",
        }
    try:
        reconnect_budget = int(reconnect_attempts)
    except (TypeError, ValueError):
        reconnect_budget = -1
    if reconnect_budget < 0:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "reconnect_attempts",
            "requested_value": reconnect_attempts,
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "Kiwoom WebSocket smoke reconnect_attempts must be a non-negative integer.",
        }
    try:
        connect_backoff = float(connect_backoff_seconds)
    except (TypeError, ValueError):
        connect_backoff = -1.0
    if connect_backoff < 0:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "connect_backoff_seconds",
            "requested_value": connect_backoff_seconds,
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "Kiwoom WebSocket smoke connect_backoff_seconds must be a non-negative number.",
        }
    try:
        reconnect_backoff = float(reconnect_backoff_seconds)
    except (TypeError, ValueError):
        reconnect_backoff = -1.0
    if reconnect_backoff < 0:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "reconnect_backoff_seconds",
            "requested_value": reconnect_backoff_seconds,
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "Kiwoom WebSocket smoke reconnect_backoff_seconds must be a non-negative number.",
        }
    try:
        subscribe_frame = build_websocket_subscribe_frame(symbols, channel=channel)
    except KoreanConnectorConfigError as exc:
        parameter = "channel" if str(channel or "").strip() not in KIWOOM_WEBSOCKET_ENDPOINTS else "symbols"
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": parameter,
            "requested_value": (
                channel
                if parameter == "channel"
                else list(symbols) if isinstance(symbols, (list, tuple)) else symbols
            ),
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": str(exc),
        }
    if transport is None:
        try:
            transport = create_websocket_transport()
        except KoreanConnectorConfigError as exc:
            return {
                "status": "not_configured",
                "connector": CONNECTOR,
                "profile": cfg.profile,
                "missing": ["websockets"],
                "network": "not_attempted",
                "error": str(exc),
            }

    endpoint = KIWOOM_WEBSOCKET_ENDPOINTS[channel]
    login_frame = build_websocket_login_frame(cfg.access_token)
    socket, connection_attempts, connect_error = await _connect_websocket_with_retries(
        transport,
        endpoint["url"],
        connect_attempts=connect_attempt_count,
        connect_backoff_seconds=connect_backoff,
    )
    total_connection_attempts = connection_attempts
    reconnects = 0
    if socket is None:
        data = subscribe_frame["data"][0]
        return {
            "status": "connection_error",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "network": "injected_transport" if injected_transport else "websocket_transport",
            "uri": endpoint["url"],
            "login": "not_attempted",
            "subscription": {"items": list(data["item"]), "types": list(data["type"])},
            "received_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "connection_attempts": total_connection_attempts,
            "reconnects": reconnects,
            "reason": f"Kiwoom WebSocket transport failed to connect after {connection_attempts} attempt(s): {connect_error}",
        }
    sample_payloads: list[dict[str, Any]] = []
    subscription_events: list[dict[str, Any]] = []
    frame_errors: list[dict[str, Any]] = []
    received_frames = 0
    try:
        await socket.send_json(login_frame)
        await socket.send_json(subscribe_frame)
        while received_frames < message_target:
            try:
                message = await _receive_websocket_message(socket, message_timeout=timeout_seconds)
            except asyncio.TimeoutError:
                data = subscribe_frame["data"][0]
                return {
                    "status": "timeout",
                    "connector": CONNECTOR,
                    "profile": cfg.profile,
                    "network": "injected_transport" if injected_transport else "websocket_transport",
                    "uri": endpoint["url"],
                    "login": "ok",
                    "subscription": {"items": list(data["item"]), "types": list(data["type"])},
                    "received_frames": received_frames,
                    "sample_payloads": sample_payloads,
                    "subscription_events": subscription_events,
                    "frame_errors": frame_errors,
                    "connection_attempts": total_connection_attempts,
                    "reconnects": reconnects,
                    "timeout_seconds": timeout_seconds,
                    "reason": "Kiwoom WebSocket smoke exceeded message_timeout while waiting for a frame.",
                }
            except Exception as exc:
                data = subscribe_frame["data"][0]
                if reconnects >= reconnect_budget:
                    return {
                        "status": "connection_error",
                        "connector": CONNECTOR,
                        "profile": cfg.profile,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": endpoint["url"],
                        "login": "ok",
                        "subscription": {"items": list(data["item"]), "types": list(data["type"])},
                        "received_frames": received_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": (
                            "Kiwoom WebSocket transport disconnected while receiving a frame: "
                            f"{str(exc) or exc.__class__.__name__}"
                        ),
                    }
                await socket.close()
                socket = None
                if reconnect_backoff:
                    await asyncio.sleep(reconnect_backoff)
                next_socket, reconnect_connection_attempts, reconnect_error = await _connect_websocket_with_retries(
                    transport,
                    endpoint["url"],
                    connect_attempts=connect_attempt_count,
                    connect_backoff_seconds=connect_backoff,
                )
                total_connection_attempts += reconnect_connection_attempts
                reconnects += 1
                if next_socket is None:
                    return {
                        "status": "connection_error",
                        "connector": CONNECTOR,
                        "profile": cfg.profile,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": endpoint["url"],
                        "login": "ok",
                        "subscription": {"items": list(data["item"]), "types": list(data["type"])},
                        "received_frames": received_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": (
                            "Kiwoom WebSocket transport failed to reconnect after "
                            f"{reconnect_connection_attempts} attempt(s): {reconnect_error}"
                        ),
                    }
                socket = next_socket
                await socket.send_json(login_frame)
                await socket.send_json(subscribe_frame)
                continue
            received_frames += 1
            if _is_websocket_frame_error(message):
                frame_error = _websocket_frame_error(message)
                frame_errors.append(frame_error)
                data = subscribe_frame["data"][0]
                return {
                    "status": "frame_error",
                    "connector": CONNECTOR,
                    "profile": cfg.profile,
                    "network": "injected_transport" if injected_transport else "websocket_transport",
                    "uri": endpoint["url"],
                    "login": "ok",
                    "subscription": {"items": list(data["item"]), "types": list(data["type"])},
                    "received_frames": received_frames,
                    "sample_payloads": sample_payloads,
                    "subscription_events": subscription_events,
                    "frame_errors": frame_errors,
                    "connection_attempts": total_connection_attempts,
                    "reconnects": reconnects,
                    "reason": f"Kiwoom WebSocket smoke received an invalid frame: {frame_error.get('error')}",
                }
            reply = websocket_control_reply(message)
            if reply is not None:
                await socket.send_json(reply)
                continue
            if str(message.get("trnm") or "").strip().upper() == endpoint["login_trnm"]:
                continue
            if str(message.get("trnm") or "").strip().upper() == endpoint["subscribe_trnm"]:
                subscription_event = _websocket_subscription_event(message)
                subscription_events.append(subscription_event)
                if subscription_event.get("status") == "error":
                    data = subscribe_frame["data"][0]
                    return {
                        "status": "subscription_error",
                        "connector": CONNECTOR,
                        "profile": cfg.profile,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": endpoint["url"],
                        "login": "ok",
                        "subscription": {"items": list(data["item"]), "types": list(data["type"])},
                        "received_frames": received_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": f"Kiwoom WebSocket subscription failed: {subscription_event.get('message')}",
                    }
                continue
            sample_payloads.append(dict(message))
    finally:
        if socket is not None:
            await socket.close()

    data = subscribe_frame["data"][0]
    return {
        "status": "ok",
        "connector": CONNECTOR,
        "profile": cfg.profile,
        "network": "injected_transport" if injected_transport else "websocket_transport",
        "uri": endpoint["url"],
        "login": "ok",
        "subscription": {"items": list(data["item"]), "types": list(data["type"])},
        "received_frames": received_frames,
        "sample_payloads": sample_payloads,
        "subscription_events": subscription_events,
        "frame_errors": frame_errors,
        "connection_attempts": total_connection_attempts,
        "reconnects": reconnects,
    }


async def _connect_websocket_with_retries(
    transport: Any,
    uri: str,
    *,
    connect_attempts: int,
    connect_backoff_seconds: float,
) -> tuple[Any | None, int, str | None]:
    try:
        attempts = max(1, int(connect_attempts))
    except (TypeError, ValueError):
        attempts = 1
    try:
        backoff_seconds = max(0.0, float(connect_backoff_seconds))
    except (TypeError, ValueError):
        backoff_seconds = 0.0

    last_error: str | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await transport.connect(uri), attempt, None
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            if attempt >= attempts:
                return None, attempt, last_error
            if backoff_seconds:
                await asyncio.sleep(backoff_seconds)
    return None, attempts, last_error


async def _receive_websocket_message(socket: Any, *, message_timeout: float | None) -> dict[str, Any]:
    receive = socket.receive_json()
    if message_timeout is None:
        return await receive
    return await asyncio.wait_for(receive, timeout=max(0.0, float(message_timeout)))


def _websockets_connect(url: str) -> Any:
    try:
        import websockets
    except ModuleNotFoundError as exc:
        raise KoreanConnectorConfigError("Kiwoom WebSocket transport requires the websockets package.") from exc
    return websockets.connect(url)


def _websocket_subscription_event(message: Mapping[str, Any]) -> dict[str, Any]:
    data_rows = _as_list(message.get("data"))
    items: list[str] = []
    types: list[str] = []
    for row in data_rows:
        if not isinstance(row, Mapping):
            continue
        items.extend(_as_scalar_values(row.get("item")))
        types.extend(_as_scalar_values(row.get("type")))
    items.extend(_as_scalar_values(message.get("items")))
    types.extend(_as_scalar_values(message.get("types")))
    try:
        item_count = len(items) or int(message.get("item_count") or 0)
    except (TypeError, ValueError):
        item_count = len(items)

    code = message.get("return_code", message.get("code"))
    code_text = str(code).strip() if code is not None else None
    event: dict[str, Any] = {
        "trnm": message.get("trnm"),
        "status": "ok" if str(code_text or "0") in {"0", ""} else "error",
        "code": code_text,
        "message": message.get("return_msg", message.get("message")),
        "group_no": message.get("grp_no", message.get("group_no")),
        "item_count": item_count,
        "types": sorted(set(types)),
    }
    return {key: value for key, value in event.items() if value not in (None, [], "")}


def _is_websocket_frame_error(message: Any) -> bool:
    if not isinstance(message, Mapping):
        return True
    if str(message.get("type") or "").strip().lower() == "error":
        return True
    if not str(message.get("trnm") or "").strip():
        return True
    return False


def _websocket_frame_error(message: Any) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        return {"status": "error", "error": "Kiwoom WebSocket frame must be a JSON object."}
    error = message.get("error") or message.get("message")
    if not error:
        error = "Kiwoom WebSocket frame missing trnm."
    return {"status": str(message.get("status") or "error"), "error": str(error)}


def websocket_smoke_evidence(result: Mapping[str, Any], *, max_samples: int = 3) -> dict[str, Any]:
    """Return a credential-safe evidence summary for a Kiwoom WebSocket smoke run."""

    source = dict(result or {})
    subscription = dict(source.get("subscription") or {}) if isinstance(source.get("subscription"), Mapping) else {}
    items = [str(item).strip() for item in subscription.get("items") or () if str(item).strip()]
    types = [str(item).strip() for item in subscription.get("types") or () if str(item).strip()]
    safe_subscription: dict[str, Any] = {
        "item_count": len(items),
        "types": types,
    }

    try:
        sample_limit = max(0, int(max_samples))
    except (TypeError, ValueError):
        sample_limit = 3
    samples = _as_list(source.get("sample_payloads"))
    subscription_events = _as_list(source.get("subscription_events"))
    frame_errors = _as_list(source.get("frame_errors"))

    evidence = {
        "status": source.get("status"),
        "connector": source.get("connector") or CONNECTOR,
        "profile": source.get("profile"),
        "environment": source.get("environment"),
        "network": source.get("network"),
        "uri": source.get("uri"),
        "login": source.get("login"),
        "subscription": safe_subscription,
        "received_frames": source.get("received_frames"),
        "subscription_events": [_websocket_subscription_event(event) for event in subscription_events],
        "frame_errors": [_websocket_frame_error(error) for error in frame_errors],
        "sample_count": len(samples),
        "sample_payloads": [_websocket_smoke_evidence_sample(sample) for sample in samples[:sample_limit]],
    }
    for key in ("reason", "timeout_seconds", "connection_attempts", "reconnects", "parameter", "requested_value"):
        if key in source:
            evidence[key] = source.get(key)
    return evidence


def write_websocket_smoke_evidence(
    result: Mapping[str, Any],
    path: str | Path,
    *,
    max_samples: int = 3,
) -> Path:
    """Write a credential-safe Kiwoom WebSocket smoke evidence JSON artifact."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence = websocket_smoke_evidence(result, max_samples=max_samples)
    target.write_text(json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return target


async def run_websocket_smoke_with_evidence(
    config: KoreanConnectorConfig | None = None,
    *,
    channel: str = "domestic_stock_realtime",
    symbols: list[str] | tuple[str, ...],
    evidence_path: str | Path,
    transport: Any | None = None,
    max_messages: int = 3,
    message_timeout: float | None = None,
    connect_attempts: int = 1,
    connect_backoff_seconds: float = 0.0,
    reconnect_attempts: int = 0,
    reconnect_backoff_seconds: float = 0.0,
    max_samples: int = 3,
    allow_broker_calls: bool = False,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Run a gated Kiwoom WebSocket smoke flow and write redacted evidence."""

    cfg = config or load_config()
    if not allow_broker_calls:
        return {
            "status": "not_run",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "reason": "Kiwoom WebSocket smoke requires allow_broker_calls=True before any credentialed broker call.",
        }
    if cfg.environment == "live" and not allow_live:
        return {
            "status": "blocked",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "reason": "Live Kiwoom WebSocket smoke requires allow_live=True.",
        }

    evidence_target = Path(evidence_path).expanduser()
    if evidence_target.exists() and evidence_target.is_dir():
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "parameter": "evidence_path",
            "requested_value": str(evidence_target),
            "reason": "Kiwoom WebSocket smoke evidence_path must be a file path, not a directory.",
        }
    if evidence_target.parent.exists() and not evidence_target.parent.is_dir():
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "parameter": "evidence_path",
            "requested_value": str(evidence_target.parent),
            "reason": "Kiwoom WebSocket smoke evidence_path parent directory must be a directory.",
        }

    result = await run_websocket_smoke(
        cfg,
        channel=channel,
        symbols=symbols,
        transport=transport,
        max_messages=max_messages,
        message_timeout=message_timeout,
        connect_attempts=connect_attempts,
        connect_backoff_seconds=connect_backoff_seconds,
        reconnect_attempts=reconnect_attempts,
        reconnect_backoff_seconds=reconnect_backoff_seconds,
    )
    written = write_websocket_smoke_evidence(result, evidence_path, max_samples=max_samples)
    evidence = websocket_smoke_evidence(result, max_samples=max_samples)
    evidence["evidence_path"] = str(written)
    return evidence


def get_account_snapshot(
    config: KoreanConnectorConfig | None = None,
    *,
    client: Any | None = None,
    exchange: str = "KRX",
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    body = {"qry_tp": "1", "dmst_stex_tp": exchange}
    payload = _request_json(cfg, "account_balance", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)
    positions = [_position_to_dict(item) for item in _as_list(payload.get("acnt_evlt_remn_indv_tot"))]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "account": {
            "cash": _to_float(payload.get("prsm_dpst_aset_amt")),
            "total_value": _to_float(payload.get("tot_evlt_amt")),
            "raw": dict(payload),
        },
        "positions": positions,
        "raw": payload,
    }


def get_positions(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    snapshot = get_account_snapshot(config, client=client)
    if snapshot.get("status") != "ok":
        return snapshot
    return {
        "status": "ok",
        "profile": snapshot.get("profile"),
        "environment": snapshot.get("environment"),
        "positions": snapshot.get("positions", []),
    }


def get_open_orders(
    config: KoreanConnectorConfig | None = None,
    *,
    include_executions: bool = False,
    client: Any | None = None,
    symbol: str = "",
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    body = {"all_stk_tp": "0", "trde_tp": "0", "stk_cd": _normalize_kr_symbol(symbol) if symbol else ""}
    payload = _request_json(cfg, "open_orders", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "orders": [_open_order_to_dict(item) for item in _as_list(payload.get("oso"))],
        "raw": payload,
    }


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, client: Any | None = None, **_: Any) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_kr_symbol(symbol)
    payload = _request_json(cfg, "stock_info", body={"stk_cd": clean}, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "quote": {
            "last": _to_float(payload.get("cur_prc")),
            "change": _to_float(payload.get("pred_pre")),
            "change_rate": _to_float(payload.get("flu_rt")),
            "volume": _to_float(payload.get("trde_qty")),
            "open": _to_float(payload.get("open_pric")),
            "high": _to_float(payload.get("high_pric")),
            "low": _to_float(payload.get("low_pric")),
            "raw": dict(payload),
        },
    }


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    client: Any | None = None,
    base_date: str | None = None,
    adjusted: bool = True,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if str(period or "1d").strip() != "1d":
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom REST currently pins only ka10081 daily bars for period='1d'."}

    clean = _normalize_kr_symbol(symbol)
    body = {"stk_cd": clean, "base_dt": base_date or date.today().strftime("%Y%m%d"), "upd_stkpc_tp": "1" if adjusted else "0"}
    payload = _request_json(cfg, "daily_chart", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    rows = _as_list(payload.get("stk_dt_pole_chart_qry"))[: int(limit)]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "period": "1d",
        "bars": [_bar_to_dict(item) for item in rows],
        "raw_summary": {key: value for key, value in payload.items() if key != "stk_dt_pole_chart_qry"},
    }


def place_order(
    config: KoreanConnectorConfig | None = None,
    *,
    symbol: str,
    side: str,
    quantity: float | None = None,
    notional: float | None = None,
    order_type: str = "market",
    limit_price: float | None = None,
    client: Any | None = None,
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom orders require quantity; notional-only orders are unsupported."}
    if notional is not None and quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom orders require explicit quantity."}

    clean_side = str(side or "").strip().lower()
    if clean_side not in ("buy", "sell"):
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom order side must be 'buy' or 'sell'."}

    clean_type = str(order_type or "market").strip().lower()
    if clean_type == "limit":
        if limit_price is None:
            return {"status": "error", "profile": cfg.profile, "error": "Kiwoom limit orders require limit_price."}
        trde_tp = "0"
        ord_uv = _numeric_string(limit_price)
    elif clean_type == "market":
        trde_tp = "3"
        ord_uv = ""
    else:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom order_type must be 'market' or 'limit'."}

    body = {
        "dmst_stex_tp": exchange,
        "stk_cd": _normalize_kr_symbol(symbol),
        "ord_qty": _numeric_string(quantity),
        "ord_uv": ord_uv,
        "trde_tp": trde_tp,
    }
    operation = "stock_buy_order" if clean_side == "buy" else "stock_sell_order"
    payload = _request_json(cfg, operation, body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["stk_cd"])
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "paper_guard": "profile_endpoint_separated",
        "symbol": body["stk_cd"],
        "side": clean_side,
        "quantity": _to_float(body["ord_qty"]),
        "order_type": clean_type,
        "order_id": payload.get("ord_no"),
        "broker_order_ref": dict(payload),
        "raw": payload,
    }


def modify_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    quantity: float | int | str | None = None,
    limit_price: float | int | str | None = None,
    client: Any | None = None,
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom modify_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom modify_order requires symbol."}
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom modify_order requires quantity."}
    if limit_price is None:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom modify_order requires limit_price."}

    body = {
        "dmst_stex_tp": exchange,
        "orig_ord_no": str(order_id).strip(),
        "stk_cd": _normalize_kr_symbol(symbol),
        "mdfy_qty": _numeric_string(quantity),
        "mdfy_uv": _numeric_string(limit_price),
        "mdfy_cond_uv": "",
    }
    payload = _request_json(cfg, "stock_modify_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["stk_cd"])
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "order_id": str(payload.get("ord_no") or order_id),
        "raw": payload,
    }


def cancel_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    quantity: float | int | str = 0,
    client: Any | None = None,
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom cancel_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "Kiwoom cancel_order requires symbol."}

    body = {
        "dmst_stex_tp": exchange,
        "orig_ord_no": str(order_id).strip(),
        "stk_cd": _normalize_kr_symbol(symbol),
        "cncl_qty": _numeric_string(quantity),
    }
    payload = _request_json(cfg, "stock_cancel_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["stk_cd"])
    return {"status": "ok", "profile": cfg.profile, "environment": cfg.environment, "order_id": order_id, "raw": payload}


def _request_json(
    config: KoreanConnectorConfig,
    operation: str,
    *,
    body: Mapping[str, Any],
    client: Any | None = None,
) -> dict[str, Any]:
    endpoint = KIWOOM_REST_ENDPOINTS[operation]
    with _client(config, client) as active:
        token = _access_token(config, active)
        url = config.endpoint.rstrip("/") + endpoint["path"]
        response = active.post(
            url,
            json=dict(body),
            headers=_headers(token, endpoint["api_id"]),
            timeout=config.timeout,
        )
        return _response_json(response)


def _access_token(config: KoreanConnectorConfig, client: Any) -> str:
    if config.access_token:
        return config.access_token
    missing = _missing_auth_fields(config)
    if missing:
        raise KoreanConnectorConfigError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")
    url = config.endpoint.rstrip("/") + KIWOOM_REST_ENDPOINTS["auth_token"]["path"]
    response = client.post(
        url,
        json={"grant_type": "client_credentials", "appkey": config.app_key, "secretkey": config.app_secret},
        headers={"Content-Type": KIWOOM_REST_ENDPOINTS["auth_token"]["content_type"]},
        timeout=config.timeout,
    )
    payload = _response_json(response)
    token = str(payload.get("token") or "").strip()
    if not token:
        raise KoreanConnectorConfigError(f"{LABEL} auth token response missing token.")
    return token


def _headers(token: str, api_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "cont-yn": "N",
        "next-key": "",
        "api-id": api_id,
    }


@contextmanager
def _client(config: KoreanConnectorConfig, client: Any | None = None) -> Iterator[Any]:
    if client is not None:
        yield client
        return
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise KoreanConnectorConfigError("Kiwoom REST calls require httpx; install project dependencies first.") from exc
    with httpx.Client(timeout=config.timeout, follow_redirects=True, trust_env=True) as active:
        yield active


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    payload = response.json()
    return dict(payload or {}) if isinstance(payload, Mapping) else {"raw": payload}


def _payload_ok(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("return_code", 0)).strip() == "0"


def _error_payload(config: KoreanConnectorConfig, payload: Mapping[str, Any], *, symbol: str | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "environment": config.environment,
        "symbol": symbol,
        "error": str(payload.get("return_msg") or payload.get("error_description") or payload.get("error") or "Kiwoom API error"),
        "code": payload.get("return_code"),
        "raw": dict(payload),
    }


def _not_configured(config: KoreanConnectorConfig, missing: list[str]) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "error": f"{LABEL} connector not configured: missing {', '.join(missing)}.",
    }


def _missing_auth_fields(config: KoreanConnectorConfig) -> list[str]:
    missing = []
    if not config.app_key:
        missing.append("app_key")
    if not config.app_secret:
        missing.append("app_secret")
    return missing


def _normalize_kr_symbol(symbol: str) -> str:
    token = str(symbol or "").strip().upper()
    if token.startswith("KRX:"):
        token = token.split(":", 1)[1]
    if token.startswith("KR."):
        token = token[3:]
    for suffix in (".KS", ".KQ"):
        if token.endswith(suffix):
            token = token[: -len(suffix)]
    return token


def _normalize_position_symbol(symbol: Any) -> str:
    token = str(symbol or "").strip().upper()
    if len(token) == 7 and token[0] in {"A", "J", "Q"} and token[1:].isdigit():
        return token[1:]
    return _normalize_kr_symbol(token)


def _position_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _normalize_position_symbol(item.get("stk_cd")),
        "name": str(item.get("stk_nm") or "").strip(),
        "quantity": _to_float(item.get("rmnd_qty")),
        "market_value": _to_float(item.get("evlt_amt")),
        "average_price": _to_float(item.get("pur_pric")),
        "raw": dict(item),
    }


def _open_order_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "order_id": str(item.get("ord_no") or "").strip(),
        "symbol": _normalize_kr_symbol(str(item.get("stk_cd") or "")),
        "quantity": _to_float(item.get("ord_qty")),
        "limit_price": _to_float(item.get("ord_pric")),
        "remaining_quantity": _to_float(item.get("oso_qty")),
        "raw": dict(item),
    }


def _condition_result_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    raw_symbol = str(item.get("9001") or "").strip()
    return {
        "symbol": _normalize_position_symbol(raw_symbol),
        "raw_symbol": raw_symbol,
        "name": str(item.get("302") or "").strip(),
        "current_price": str(item.get("10") or "").strip(),
        "change_sign": str(item.get("25") or "").strip(),
        "change": str(item.get("11") or "").strip(),
        "change_rate": str(item.get("12") or "").strip(),
        "volume": str(item.get("13") or "").strip(),
        "open": str(item.get("16") or "").strip(),
        "high": str(item.get("17") or "").strip(),
        "low": str(item.get("18") or "").strip(),
        "raw": dict(item),
    }


def _condition_realtime_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    values = item.get("values")
    clean_values = dict(values) if isinstance(values, Mapping) else {}
    raw_symbol = str(clean_values.get("9001") or item.get("name") or "").strip()
    return {
        "type": str(item.get("type") or "").strip(),
        "name": str(item.get("name") or "").strip(),
        "seq": str(clean_values.get("841") or "").strip(),
        "symbol": _normalize_position_symbol(raw_symbol),
        "action": str(clean_values.get("843") or "").strip(),
        "trade_time": str(clean_values.get("20") or "").strip(),
        "side": str(clean_values.get("907") or "").strip(),
        "values": clean_values,
        "raw": dict(item),
    }


def _bar_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "date": item.get("dt"),
        "open": _to_float(item.get("open_pric")),
        "high": _to_float(item.get("high_pric")),
        "low": _to_float(item.get("low_pric")),
        "close": _to_float(item.get("cur_prc")),
        "volume": _to_float(item.get("trde_qty")),
        "raw": dict(item),
    }


def _as_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def _as_scalar_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _websocket_smoke_evidence_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("trnm", "status", "channel", "type"):
        if key in sample:
            safe[key] = sample.get(key)

    data = sample.get("data")
    if isinstance(data, Mapping):
        rows = [data]
    elif isinstance(data, list):
        rows = [item for item in data if isinstance(item, Mapping)]
    else:
        rows = []
    if rows:
        safe["data_count"] = len(rows)
        safe["data_keys"] = sorted({str(key) for row in rows for key in row})

    raw = sample.get("raw")
    if isinstance(raw, Mapping):
        safe["raw_keys"] = sorted(str(key) for key in raw)

    return redact_payload(safe)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _to_abs_float(value: Any) -> float | None:
    parsed = _to_float(value)
    return abs(parsed) if parsed is not None else None


def _orderbook_level(values: Mapping[str, Any], level: int, *, side: str) -> dict[str, Any]:
    if side == "ask":
        price_fid = str(40 + level)
        quantity_fid = str(60 + level)
        change_fid = str(80 + level)
        lp_fid = str(620 + level)
        krx_fid = str(6043 + level)
        nxt_fid = str(6065 + level)
    else:
        price_fid = str(50 + level)
        quantity_fid = str(70 + level)
        change_fid = str(90 + level)
        lp_fid = str(630 + level)
        krx_fid = str(6053 + level)
        nxt_fid = str(6075 + level)
    return {
        "level": level,
        "price": _to_abs_float(values.get(price_fid)),
        "quantity": _to_float(values.get(quantity_fid)),
        "change": _to_float(values.get(change_fid)),
        "krx_quantity": _to_float(values.get(krx_fid)),
        "nxt_quantity": _to_float(values.get(nxt_fid)),
        "lp_quantity": _to_float(values.get(lp_fid)),
    }


def _signed_volume_side(value: Any) -> str | None:
    token = str(value or "").strip()
    if token.startswith("+"):
        return "buy"
    if token.startswith("-"):
        return "sell"
    return None


def _numeric_string(value: float | int | str) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)
