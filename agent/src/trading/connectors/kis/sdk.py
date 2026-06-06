"""KIS Open API connector.

The endpoint catalog and TR IDs are derived from Korea Investment & Securities'
official ``open-trading-api`` samples. This module does not vendor that code;
it implements Vibe-Trading's own small REST adapter around the official
contract.
"""

from __future__ import annotations

import asyncio
from base64 import b64decode
import json
from contextlib import contextmanager
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

CONFIG_FILENAME = "kis.json"
PAPER_URL = "https://openapivts.koreainvestment.com:29443"
LIVE_URL = "https://openapi.koreainvestment.com:9443"
LABEL = "KIS Open API"
CONNECTOR = "kis"

KIS_DOMESTIC_STOCK_ENDPOINTS: dict[str, dict[str, str]] = {
    "websocket_approval": {
        "method": "POST",
        "path": "/oauth2/Approval",
    },
    "auth_token": {
        "method": "POST",
        "path": "/oauth2/tokenP",
    },
    "hashkey": {
        "method": "POST",
        "path": "/uapi/hashkey",
    },
    "inquire_price": {
        "method": "GET",
        "path": "/uapi/domestic-stock/v1/quotations/inquire-price",
        "tr_id": "FHKST01010100",
    },
    "inquire_daily_itemchartprice": {
        "method": "GET",
        "path": "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        "tr_id": "FHKST03010100",
    },
    "inquire_balance": {
        "method": "GET",
        "path": "/uapi/domestic-stock/v1/trading/inquire-balance",
        "live_tr_id": "TTTC8434R",
        "paper_tr_id": "VTTC8434R",
    },
    "inquire_psbl_rvsecncl": {
        "method": "GET",
        "path": "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl",
        "tr_id": "TTTC0084R",
    },
    "order_cash": {
        "method": "POST",
        "path": "/uapi/domestic-stock/v1/trading/order-cash",
        "live_sell_tr_id": "TTTC0011U",
        "live_buy_tr_id": "TTTC0012U",
        "paper_sell_tr_id": "VTTC0011U",
        "paper_buy_tr_id": "VTTC0012U",
    },
    "order_rvsecncl": {
        "method": "POST",
        "path": "/uapi/domestic-stock/v1/trading/order-rvsecncl",
        "live_tr_id": "TTTC0013U",
        "paper_tr_id": "VTTC0013U",
    },
}

KIS_WEBSOCKET_URLS: dict[str, str] = {
    "paper": "ws://ops.koreainvestment.com:31000",
    "live": "ws://ops.koreainvestment.com:21000",
}

KIS_WEBSOCKET_CHANNELS: dict[str, dict[str, str]] = {
    "asking_price_krx": {"tr_id": "H0STASP0", "tr_key": "symbol", "kind": "orderbook"},
    "asking_price_nxt": {"tr_id": "H0NXASP0", "tr_key": "symbol", "kind": "orderbook"},
    "asking_price_total": {"tr_id": "H0UNASP0", "tr_key": "symbol", "kind": "orderbook"},
    "ccnl_krx": {"tr_id": "H0STCNT0", "tr_key": "symbol", "kind": "trade"},
    "ccnl_notice": {
        "live_tr_id": "H0STCNI0",
        "paper_tr_id": "H0STCNI9",
        "tr_key": "hts_id",
        "kind": "order_notice",
        "encrypted": "Y",
    },
    "ccnl_nxt": {"tr_id": "H0NXCNT0", "tr_key": "symbol", "kind": "trade"},
    "ccnl_total": {"tr_id": "H0UNCNT0", "tr_key": "symbol", "kind": "trade"},
    "exp_ccnl_krx": {"tr_id": "H0STANC0", "tr_key": "symbol", "kind": "expected_trade"},
    "exp_ccnl_nxt": {"tr_id": "H0NXANC0", "tr_key": "symbol", "kind": "expected_trade"},
    "exp_ccnl_total": {"tr_id": "H0UNANC0", "tr_key": "symbol", "kind": "expected_trade"},
    "index_ccnl": {"tr_id": "H0UPCNT0", "tr_key": "index", "kind": "index_trade"},
    "index_exp_ccnl": {"tr_id": "H0UPANC0", "tr_key": "index", "kind": "index_expected_trade"},
    "index_program_trade": {"tr_id": "H0UPPGM0", "tr_key": "index", "kind": "index_program_trade"},
    "market_status_krx": {"tr_id": "H0STMKO0", "tr_key": "symbol", "kind": "market_status"},
    "market_status_nxt": {"tr_id": "H0NXMKO0", "tr_key": "symbol", "kind": "market_status"},
    "market_status_total": {"tr_id": "H0UNMKO0", "tr_key": "symbol", "kind": "market_status"},
    "member_krx": {"tr_id": "H0STMBC0", "tr_key": "symbol", "kind": "member"},
    "member_nxt": {"tr_id": "H0NXMBC0", "tr_key": "symbol", "kind": "member"},
    "member_total": {"tr_id": "H0UNMBC0", "tr_key": "symbol", "kind": "member"},
    "overtime_asking_price_krx": {"tr_id": "H0STOAA0", "tr_key": "symbol", "kind": "orderbook"},
    "overtime_ccnl_krx": {"tr_id": "H0STOUP0", "tr_key": "symbol", "kind": "trade"},
    "overtime_exp_ccnl_krx": {"tr_id": "H0STOAC0", "tr_key": "symbol", "kind": "expected_trade"},
    "program_trade_krx": {"tr_id": "H0STPGM0", "tr_key": "symbol", "kind": "program_trade"},
    "program_trade_nxt": {"tr_id": "H0NXPGM0", "tr_key": "symbol", "kind": "program_trade"},
    "program_trade_total": {"tr_id": "H0UNPGM0", "tr_key": "symbol", "kind": "program_trade"},
}

_KIS_TRADE_COLUMNS = [
    "MKSC_SHRN_ISCD",
    "STCK_CNTG_HOUR",
    "STCK_PRPR",
    "PRDY_VRSS_SIGN",
    "PRDY_VRSS",
    "PRDY_CTRT",
    "WGHN_AVRG_STCK_PRC",
    "STCK_OPRC",
    "STCK_HGPR",
    "STCK_LWPR",
    "ASKP1",
    "BIDP1",
    "CNTG_VOL",
    "ACML_VOL",
    "ACML_TR_PBMN",
    "SELN_CNTG_CSNU",
    "SHNU_CNTG_CSNU",
    "NTBY_CNTG_CSNU",
    "CTTR",
    "SELN_CNTG_SMTN",
    "SHNU_CNTG_SMTN",
    "CCLD_DVSN",
    "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE",
    "OPRC_HOUR",
    "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR",
    "HGPR_HOUR",
    "HGPR_VRSS_PRPR_SIGN",
    "HGPR_VRSS_PRPR",
    "LWPR_HOUR",
    "LWPR_VRSS_PRPR_SIGN",
    "LWPR_VRSS_PRPR",
    "BSOP_DATE",
    "NEW_MKOP_CLS_CODE",
    "TRHT_YN",
    "ASKP_RSQN1",
    "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN",
    "TOTAL_BIDP_RSQN",
    "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL",
    "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE",
    "MRKT_TRTM_CLS_CODE",
    "VI_STND_PRC",
]

KIS_WEBSOCKET_TRADE_FIELDS = tuple(_KIS_TRADE_COLUMNS)

_KIS_ORDERBOOK_COLUMNS = [
    "MKSC_SHRN_ISCD",
    "BSOP_HOUR",
    "HOUR_CLS_CODE",
    "ASKP1",
    "ASKP2",
    "ASKP3",
    "ASKP4",
    "ASKP5",
    "ASKP6",
    "ASKP7",
    "ASKP8",
    "ASKP9",
    "ASKP10",
    "BIDP1",
    "BIDP2",
    "BIDP3",
    "BIDP4",
    "BIDP5",
    "BIDP6",
    "BIDP7",
    "BIDP8",
    "BIDP9",
    "BIDP10",
    "ASKP_RSQN1",
    "ASKP_RSQN2",
    "ASKP_RSQN3",
    "ASKP_RSQN4",
    "ASKP_RSQN5",
    "ASKP_RSQN6",
    "ASKP_RSQN7",
    "ASKP_RSQN8",
    "ASKP_RSQN9",
    "ASKP_RSQN10",
    "BIDP_RSQN1",
    "BIDP_RSQN2",
    "BIDP_RSQN3",
    "BIDP_RSQN4",
    "BIDP_RSQN5",
    "BIDP_RSQN6",
    "BIDP_RSQN7",
    "BIDP_RSQN8",
    "BIDP_RSQN9",
    "BIDP_RSQN10",
    "TOTAL_ASKP_RSQN",
    "TOTAL_BIDP_RSQN",
    "OVTM_TOTAL_ASKP_RSQN",
    "OVTM_TOTAL_BIDP_RSQN",
    "ANTC_CNPR",
    "ANTC_CNQN",
    "ANTC_VOL",
    "ANTC_CNTG_VRSS",
    "ANTC_CNTG_VRSS_SIGN",
    "ANTC_CNTG_PRDY_CTRT",
    "ACML_VOL",
    "TOTAL_ASKP_RSQN_ICDC",
    "TOTAL_BIDP_RSQN_ICDC",
    "OVTM_TOTAL_ASKP_ICDC",
    "OVTM_TOTAL_BIDP_ICDC",
    "STCK_DEAL_CLS_CODE",
]

KIS_WEBSOCKET_ORDERBOOK_FIELDS = tuple(_KIS_ORDERBOOK_COLUMNS)

_KIS_NOTICE_COLUMNS = [
    "CUST_ID",
    "ACNT_NO",
    "ODER_NO",
    "OODER_NO",
    "SELN_BYOV_CLS",
    "RCTF_CLS",
    "ODER_KIND",
    "ODER_COND",
    "STCK_SHRN_ISCD",
    "CNTG_QTY",
    "CNTG_UNPR",
    "STCK_CNTG_HOUR",
    "RFUS_YN",
    "CNTG_YN",
    "ACPT_YN",
    "BRNC_NO",
    "ODER_QTY",
    "ACNT_NAME",
    "ORD_COND_PRC",
    "ORD_EXG_GB",
    "POPUP_YN",
    "FILLER",
    "CRDT_CLS",
    "CRDT_LOAN_DATE",
    "CNTG_ISNM40",
    "ODER_PRC",
]

KIS_WEBSOCKET_NOTICE_FIELDS = tuple(_KIS_NOTICE_COLUMNS)

KIS_WEBSOCKET_COLUMNS: dict[str, list[str]] = {
    "H0STASP0": _KIS_ORDERBOOK_COLUMNS,
    "H0STCNT0": _KIS_TRADE_COLUMNS,
    "H0STCNI0": _KIS_NOTICE_COLUMNS,
    "H0STCNI9": _KIS_NOTICE_COLUMNS,
}

_PERIOD_MAP = {"1d": "D", "1w": "W", "1M": "M", "1mo": "M", "1y": "Y"}


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
    report["auth_probe_reason"] = "KIS token issuance can trigger broker notifications; explicit reads/orders perform auth."
    report["official_catalog"] = (
        "domestic_stock REST and WebSocket: FHKST01010100,FHKST03010100,TTTC8434R,VTTC8434R,"
        "TTTC0011U,TTTC0012U,VTTC0011U,VTTC0012U,TTTC0013U,VTTC0013U,"
        "H0STASP0,H0NXASP0,H0UNASP0,H0STCNT0,H0NXCNT0,H0UNCNT0,H0STCNI0,H0STCNI9"
    )
    return report


def get_account_snapshot(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_account_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    params = {
        "CANO": cfg.account,
        "ACNT_PRDT_CD": cfg.account_product_code,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    tr_id = _tr_id("inquire_balance", cfg)
    payload = _request_json(cfg, "GET", "inquire_balance", tr_id=tr_id, params=params, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)

    raw_positions = _as_list(payload.get("output1"))
    raw_account = _first_mapping(payload.get("output2"))
    positions = [_position_to_dict(item) for item in raw_positions]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "account_ref": _account_ref(cfg),
        "account": {
            "cash": _to_float(raw_account.get("dnca_tot_amt")),
            "total_value": _to_float(raw_account.get("tot_evlu_amt")),
            "raw": raw_account,
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
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_account_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    params = {
        "CANO": cfg.account,
        "ACNT_PRDT_CD": cfg.account_product_code,
        "INQR_DVSN_1": "1",
        "INQR_DVSN_2": "0",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    tr_id = KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_psbl_rvsecncl"]["tr_id"]
    payload = _request_json(cfg, "GET", "inquire_psbl_rvsecncl", tr_id=tr_id, params=params, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "include_executions": include_executions,
        "orders": [_open_order_to_dict(item) for item in _as_list(payload.get("output"))],
        "raw": payload,
    }


def websocket_url(config: KoreanConnectorConfig | None = None) -> str:
    """Return KIS' official WebSocket endpoint for the active profile."""

    cfg = config or load_config()
    return KIS_WEBSOCKET_URLS["paper"] if cfg.environment == "paper" else KIS_WEBSOCKET_URLS["live"]


def issue_websocket_approval_key(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> str:
    """Issue the KIS WebSocket approval key used in official real-time samples."""

    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        raise KoreanConnectorConfigError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")

    body = {
        "grant_type": "client_credentials",
        "appkey": cfg.app_key,
        "secretkey": cfg.app_secret,
    }
    headers = {"Content-Type": "application/json", "Accept": "text/plain", "charset": "UTF-8"}
    with _client(cfg, client) as active:
        url = cfg.endpoint.rstrip("/") + KIS_DOMESTIC_STOCK_ENDPOINTS["websocket_approval"]["path"]
        response = active.post(url, json=body, headers=headers, timeout=cfg.timeout)
        payload = _response_json(response)
    approval_key = str(payload.get("approval_key") or "").strip()
    if not approval_key:
        raise KoreanConnectorConfigError(f"{LABEL} WebSocket approval response missing approval_key.")
    return approval_key


def build_websocket_subscribe_message(
    tr_key: str,
    *,
    channel: str,
    approval_key: str,
    config: KoreanConnectorConfig | None = None,
    tr_type: str = "1",
    append_headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the official KIS ``data_fetch`` style WebSocket message."""

    cfg = config or load_config()
    spec = _websocket_channel(channel)
    key = str(tr_key or "").strip()
    if spec.get("tr_key") == "symbol":
        key = _normalize_kr_symbol(key)
    if not key:
        raise KoreanConnectorConfigError(f"KIS WebSocket channel {channel!r} requires a tr_key.")
    if not str(approval_key or "").strip():
        raise KoreanConnectorConfigError("KIS WebSocket subscriptions require an approval_key from /oauth2/Approval.")

    headers: dict[str, str] = {
        "content-type": "utf-8",
        "approval_key": str(approval_key).strip(),
        "tr_type": str(tr_type or "1"),
        "custtype": "P",
    }
    for header_key, value in dict(append_headers or {}).items():
        headers[str(header_key)] = str(value)

    return {
        "header": headers,
        "body": {"input": {"tr_id": _websocket_tr_id(spec, cfg), "tr_key": key}},
    }


def parse_websocket_message(message: str | bytes, *, channel: str | None = None) -> dict[str, Any]:
    """Normalize KIS WebSocket data and system frames into stable dictionaries."""

    raw = message.decode("utf-8") if isinstance(message, bytes) else str(message or "")
    if not raw:
        return {"type": "error", "status": "error", "error": "empty KIS WebSocket message"}
    if raw[0] in ("0", "1"):
        parts = raw.split("|", 3)
        if len(parts) < 4:
            return {"type": "error", "status": "error", "raw": raw, "error": "malformed KIS data frame"}
        tr_id = parts[1]
        values = parts[3].split("^") if parts[3] else []
        columns = KIS_WEBSOCKET_COLUMNS.get(tr_id, [])
        if not columns and channel:
            columns = _websocket_columns_for_channel(channel)
        fields = {name: values[idx] for idx, name in enumerate(columns) if idx < len(values)}
        return {
            "type": "data",
            "status": "ok",
            "prefix": parts[0],
            "tr_id": tr_id,
            "sequence": parts[2],
            "fields": fields,
            "raw_values": values,
            "event": _websocket_event(tr_id, fields),
        }

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"type": "error", "status": "error", "raw": raw, "error": str(exc)}

    header = dict(payload.get("header") or {}) if isinstance(payload, Mapping) else {}
    body = dict(payload.get("body") or {}) if isinstance(payload, Mapping) else {}
    output = dict(body.get("output") or {}) if isinstance(body.get("output"), Mapping) else {}
    status = "ok" if str(body.get("rt_cd", "0")) == "0" else "error"
    return {
        "type": "system",
        "status": status,
        "tr_id": header.get("tr_id"),
        "tr_key": header.get("tr_key"),
        "message": body.get("msg1"),
        "is_pingpong": header.get("tr_id") == "PINGPONG",
        "encrypted": str(header.get("encrypt") or "").upper() == "Y",
        "iv": output.get("iv"),
        "key": output.get("key"),
        "raw": payload,
    }


def parse_websocket_trade_ticks(message: str | bytes) -> list[dict[str, Any]]:
    """Parse official KIS ``H0STCNT0`` domestic stock trade frames."""

    raw = message.decode("utf-8") if isinstance(message, bytes) else str(message or "")
    parts = raw.split("|", 3)
    if len(parts) < 4:
        raise KoreanConnectorConfigError("KIS WebSocket trade tick parser expected H0STCNT0 data frame.")
    prefix, tr_id, count_token, payload = parts
    if prefix != "0" or tr_id != "H0STCNT0":
        raise KoreanConnectorConfigError(f"KIS WebSocket trade tick parser expected H0STCNT0, got {tr_id or 'missing'}.")
    try:
        declared_count = int(count_token)
    except ValueError as exc:
        raise KoreanConnectorConfigError(f"KIS WebSocket trade tick parser received invalid H0STCNT0 count {count_token!r}.") from exc
    if declared_count <= 0:
        raise KoreanConnectorConfigError("KIS WebSocket trade tick parser expected at least one H0STCNT0 tick.")

    values = payload.split("^") if payload else []
    field_count = len(KIS_WEBSOCKET_TRADE_FIELDS)
    expected_values = declared_count * field_count
    if len(values) != expected_values:
        raise KoreanConnectorConfigError(
            f"KIS WebSocket trade tick parser expected {field_count} values per H0STCNT0 tick "
            f"and {declared_count} ticks, got {len(values)} values."
        )

    ticks: list[dict[str, Any]] = []
    for index in range(declared_count):
        start = index * field_count
        row_values = values[start : start + field_count]
        fields = {name: row_values[pos] for pos, name in enumerate(KIS_WEBSOCKET_TRADE_FIELDS)}
        ticks.append(_websocket_trade_tick(fields, row_values))
    return ticks


def parse_websocket_orderbooks(message: str | bytes) -> list[dict[str, Any]]:
    """Parse official KIS ``H0STASP0`` domestic stock orderbook frames."""

    raw = message.decode("utf-8") if isinstance(message, bytes) else str(message or "")
    parts = raw.split("|", 3)
    if len(parts) < 4:
        raise KoreanConnectorConfigError("KIS WebSocket orderbook parser expected H0STASP0 data frame.")
    prefix, tr_id, count_token, payload = parts
    if prefix != "0" or tr_id != "H0STASP0":
        raise KoreanConnectorConfigError(f"KIS WebSocket orderbook parser expected H0STASP0, got {tr_id or 'missing'}.")
    try:
        declared_count = int(count_token)
    except ValueError as exc:
        raise KoreanConnectorConfigError(f"KIS WebSocket orderbook parser received invalid H0STASP0 count {count_token!r}.") from exc
    if declared_count <= 0:
        raise KoreanConnectorConfigError("KIS WebSocket orderbook parser expected at least one H0STASP0 book.")

    values = payload.split("^") if payload else []
    field_count = len(KIS_WEBSOCKET_ORDERBOOK_FIELDS)
    expected_values = declared_count * field_count
    if len(values) != expected_values:
        raise KoreanConnectorConfigError(
            f"KIS WebSocket orderbook parser expected {field_count} values per H0STASP0 book "
            f"and {declared_count} books, got {len(values)} values."
        )

    books: list[dict[str, Any]] = []
    for index in range(declared_count):
        start = index * field_count
        row_values = values[start : start + field_count]
        fields = {name: row_values[pos] for pos, name in enumerate(KIS_WEBSOCKET_ORDERBOOK_FIELDS)}
        books.append(_websocket_orderbook(fields, row_values))
    return books


def websocket_pingpong_payload(message: str | bytes) -> str | bytes | None:
    """Return the raw KIS PINGPONG payload callers should send as ``pong``."""

    parsed = parse_websocket_message(message)
    if parsed.get("type") == "system" and parsed.get("is_pingpong") is True:
        return message
    return None


class KisWebSocketConnection:
    """Small adapter around a real WebSocket client connection."""

    def __init__(self, socket: Any, manager: Any | None = None):
        self._socket = socket
        self._manager = manager

    async def send_json(self, payload: Mapping[str, Any]) -> None:
        await self._socket.send(json.dumps(payload, ensure_ascii=False))

    async def receive(self) -> str | bytes:
        return await self._socket.recv()

    async def pong(self, payload: str | bytes) -> None:
        await self._socket.pong(payload)

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
            return
        await self._socket.close()


class KisWebSocketTransport:
    """Connect to KIS' official WebSocket endpoint using ``websockets``."""

    def __init__(self, connect_factory: Any | None = None):
        self._connect_factory = connect_factory or _websockets_connect

    async def connect(self, url: str) -> KisWebSocketConnection:
        connection = self._connect_factory(url)
        if hasattr(connection, "__await__"):
            return KisWebSocketConnection(await connection)
        if hasattr(connection, "__aenter__"):
            return KisWebSocketConnection(await connection.__aenter__(), manager=connection)
        return KisWebSocketConnection(connection)


def create_websocket_transport() -> KisWebSocketTransport:
    """Return the default KIS WebSocket transport."""

    return KisWebSocketTransport()


async def run_websocket_smoke(
    config: KoreanConnectorConfig | None = None,
    *,
    channel: str,
    tr_key: str,
    client: Any | None = None,
    transport: Any | None = None,
    max_messages: int = 3,
    message_timeout: float | None = None,
    connect_attempts: int = 1,
    connect_backoff_seconds: float = 0.0,
    reconnect_attempts: int = 0,
    reconnect_backoff_seconds: float = 0.0,
) -> dict[str, Any]:
    """Run a KIS WebSocket smoke flow."""

    cfg = config or load_config()
    injected_transport = transport is not None
    missing = _missing_auth_fields(cfg)
    if missing:
        return {
            "status": "not_configured",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "missing": missing,
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
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke max_messages must be a positive integer.",
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
                "pong_frames": 0,
                "sample_payloads": [],
                "subscription_events": [],
                "frame_errors": [],
                "reason": "KIS WebSocket smoke message_timeout must be a positive number.",
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
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke connect_attempts must be a positive integer.",
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
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke reconnect_attempts must be a non-negative integer.",
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
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke connect_backoff_seconds must be a non-negative number.",
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
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke reconnect_backoff_seconds must be a non-negative number.",
        }
    channel_key = str(channel or "").strip().lower()
    channel_spec = KIS_WEBSOCKET_CHANNELS.get(channel_key)
    if channel_spec is None:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "channel",
            "requested_value": channel,
            "received_frames": 0,
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": "KIS WebSocket smoke channel must be a supported KIS WebSocket channel.",
        }
    normalized_tr_key = str(tr_key or "").strip()
    if channel_spec.get("tr_key") == "symbol":
        normalized_tr_key = _normalize_kr_symbol(normalized_tr_key)
    if not normalized_tr_key:
        return {
            "status": "invalid_request",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "parameter": "tr_key",
            "requested_value": tr_key,
            "received_frames": 0,
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": f"KIS WebSocket channel {channel!r} requires a tr_key.",
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

    try:
        approval_key = issue_websocket_approval_key(cfg, client=client)
    except Exception as exc:
        return {
            "status": "approval_error",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "approval_request",
            "approval": "failed",
            "received_frames": 0,
            "pong_frames": 0,
            "sample_payloads": [],
            "subscription_events": [],
            "frame_errors": [],
            "reason": f"KIS WebSocket approval-key request failed: {str(exc) or exc.__class__.__name__}",
        }
    subscription = build_websocket_subscribe_message(tr_key, channel=channel, approval_key=approval_key, config=cfg)
    uri = websocket_url(cfg)
    socket, connection_attempts, connect_error = await _connect_websocket_with_retries(
        transport,
        uri,
        connect_attempts=connect_attempt_count,
        connect_backoff_seconds=connect_backoff,
    )
    total_connection_attempts = connection_attempts
    reconnects = 0
    input_spec = dict(subscription["body"]["input"])
    if socket is None:
        return {
            "status": "connection_error",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "injected_transport" if injected_transport else "websocket_transport",
            "uri": uri,
            "approval": "issued",
            "subscription": {"channel": channel, "tr_id": input_spec["tr_id"], "tr_key": input_spec["tr_key"]},
            "received_frames": 0,
            "pong_frames": 0,
            "sample_payloads": [],
            "frame_errors": [],
            "connection_attempts": total_connection_attempts,
            "reconnects": reconnects,
            "reason": f"KIS WebSocket transport failed to connect after {connection_attempts} attempt(s): {connect_error}",
        }
    sample_payloads: list[dict[str, Any]] = []
    subscription_events: list[dict[str, Any]] = []
    frame_errors: list[dict[str, Any]] = []
    received_frames = 0
    pong_frames = 0
    try:
        await socket.send_json(subscription)
        while received_frames < message_target:
            try:
                raw = await _receive_websocket_message(socket, message_timeout=timeout_seconds)
            except asyncio.TimeoutError:
                return {
                    "status": "timeout",
                    "connector": CONNECTOR,
                    "profile": cfg.profile,
                    "environment": cfg.environment,
                    "network": "injected_transport" if injected_transport else "websocket_transport",
                    "uri": websocket_url(cfg),
                    "approval": "issued",
                    "subscription": {"channel": channel, "tr_id": input_spec["tr_id"], "tr_key": input_spec["tr_key"]},
                    "received_frames": received_frames,
                    "pong_frames": pong_frames,
                    "sample_payloads": sample_payloads,
                    "subscription_events": subscription_events,
                    "frame_errors": frame_errors,
                    "connection_attempts": total_connection_attempts,
                    "reconnects": reconnects,
                    "timeout_seconds": timeout_seconds,
                    "reason": "KIS WebSocket smoke exceeded message_timeout while waiting for a frame.",
                }
            except Exception as exc:
                if reconnects >= reconnect_budget:
                    return {
                        "status": "connection_error",
                        "connector": CONNECTOR,
                        "profile": cfg.profile,
                        "environment": cfg.environment,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": websocket_url(cfg),
                        "approval": "issued",
                        "subscription": {
                            "channel": channel,
                            "tr_id": input_spec["tr_id"],
                            "tr_key": input_spec["tr_key"],
                        },
                        "received_frames": received_frames,
                        "pong_frames": pong_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": (
                            "KIS WebSocket transport disconnected while receiving a frame: "
                            f"{str(exc) or exc.__class__.__name__}"
                        ),
                    }
                await socket.close()
                socket = None
                if reconnect_backoff:
                    await asyncio.sleep(reconnect_backoff)
                next_socket, reconnect_connection_attempts, reconnect_error = await _connect_websocket_with_retries(
                    transport,
                    uri,
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
                        "environment": cfg.environment,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": websocket_url(cfg),
                        "approval": "issued",
                        "subscription": {
                            "channel": channel,
                            "tr_id": input_spec["tr_id"],
                            "tr_key": input_spec["tr_key"],
                        },
                        "received_frames": received_frames,
                        "pong_frames": pong_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": (
                            "KIS WebSocket transport failed to reconnect after "
                            f"{reconnect_connection_attempts} attempt(s): {reconnect_error}"
                        ),
                    }
                socket = next_socket
                await socket.send_json(subscription)
                continue
            received_frames += 1
            pong_payload = websocket_pingpong_payload(raw)
            if pong_payload is not None:
                await socket.pong(pong_payload)
                pong_frames += 1
                continue
            parsed = parse_websocket_message(raw, channel=channel)
            if parsed.get("type") == "error":
                frame_error = _websocket_frame_error(parsed)
                frame_errors.append(frame_error)
                return {
                    "status": "frame_error",
                    "connector": CONNECTOR,
                    "profile": cfg.profile,
                    "environment": cfg.environment,
                    "network": "injected_transport" if injected_transport else "websocket_transport",
                    "uri": websocket_url(cfg),
                    "approval": "issued",
                    "subscription": {
                        "channel": channel,
                        "tr_id": input_spec["tr_id"],
                        "tr_key": input_spec["tr_key"],
                    },
                    "received_frames": received_frames,
                    "pong_frames": pong_frames,
                    "sample_payloads": sample_payloads,
                    "subscription_events": subscription_events,
                    "frame_errors": frame_errors,
                    "connection_attempts": total_connection_attempts,
                    "reconnects": reconnects,
                    "reason": f"KIS WebSocket smoke received an invalid frame: {frame_error.get('error')}",
                }
            if parsed.get("type") == "system":
                subscription_event = _websocket_subscription_event(parsed)
                subscription_events.append(subscription_event)
                if subscription_event.get("status") == "error":
                    return {
                        "status": "subscription_error",
                        "connector": CONNECTOR,
                        "profile": cfg.profile,
                        "environment": cfg.environment,
                        "network": "injected_transport" if injected_transport else "websocket_transport",
                        "uri": websocket_url(cfg),
                        "approval": "issued",
                        "subscription": {
                            "channel": channel,
                            "tr_id": input_spec["tr_id"],
                            "tr_key": input_spec["tr_key"],
                        },
                        "received_frames": received_frames,
                        "pong_frames": pong_frames,
                        "sample_payloads": sample_payloads,
                        "subscription_events": subscription_events,
                        "frame_errors": frame_errors,
                        "connection_attempts": total_connection_attempts,
                        "reconnects": reconnects,
                        "reason": f"KIS WebSocket subscription failed: {subscription_event.get('message')}",
                    }
            if parsed.get("type") == "data":
                sample_payloads.append(parsed)
    finally:
        if socket is not None:
            await socket.close()

    return {
        "status": "ok",
        "connector": CONNECTOR,
        "profile": cfg.profile,
        "environment": cfg.environment,
        "network": "injected_transport" if injected_transport else "websocket_transport",
        "uri": websocket_url(cfg),
        "approval": "issued",
        "subscription": {"channel": channel, "tr_id": input_spec["tr_id"], "tr_key": input_spec["tr_key"]},
        "received_frames": received_frames,
        "pong_frames": pong_frames,
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


async def _receive_websocket_message(socket: Any, *, message_timeout: float | None) -> str | bytes:
    receive = socket.receive()
    if message_timeout is None:
        return await receive
    return await asyncio.wait_for(receive, timeout=max(0.0, float(message_timeout)))


def _websocket_subscription_event(parsed: Mapping[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "tr_id": parsed.get("tr_id"),
        "status": parsed.get("status"),
        "message": parsed.get("message"),
        "encrypted": bool(parsed.get("encrypted")),
        "iv_present": bool(parsed.get("iv_present") or parsed.get("iv")),
        "key_present": bool(parsed.get("key_present") or parsed.get("key")),
    }
    return {key: value for key, value in event.items() if value is not None}


def _websocket_frame_error(parsed: Mapping[str, Any]) -> dict[str, Any]:
    error = parsed.get("error") or parsed.get("message") or "invalid KIS WebSocket frame"
    return {"status": str(parsed.get("status") or "error"), "error": str(error)}


def _websockets_connect(url: str) -> Any:
    try:
        import websockets
    except ModuleNotFoundError as exc:
        raise KoreanConnectorConfigError("KIS WebSocket transport requires the websockets package.") from exc
    return websockets.connect(url)


def websocket_smoke_evidence(result: Mapping[str, Any], *, max_samples: int = 3) -> dict[str, Any]:
    """Return a credential-safe evidence summary for a KIS WebSocket smoke run."""

    source = dict(result or {})
    subscription = dict(source.get("subscription") or {}) if isinstance(source.get("subscription"), Mapping) else {}
    channel = str(subscription.get("channel") or "").strip()
    channel_spec = KIS_WEBSOCKET_CHANNELS.get(channel.lower(), {})
    safe_subscription: dict[str, Any] = {
        "channel": subscription.get("channel"),
        "tr_id": subscription.get("tr_id"),
        "tr_key_present": bool(subscription.get("tr_key")),
    }
    if channel_spec.get("tr_key"):
        safe_subscription["tr_key_kind"] = channel_spec["tr_key"]

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
        "approval": source.get("approval"),
        "subscription": safe_subscription,
        "received_frames": source.get("received_frames"),
        "pong_frames": source.get("pong_frames"),
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
    """Write a credential-safe KIS WebSocket smoke evidence JSON artifact."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    evidence = websocket_smoke_evidence(result, max_samples=max_samples)
    target.write_text(json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return target


async def run_websocket_smoke_with_evidence(
    config: KoreanConnectorConfig | None = None,
    *,
    channel: str,
    tr_key: str,
    evidence_path: str | Path,
    client: Any | None = None,
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
    """Run a gated KIS WebSocket smoke flow and write redacted evidence."""

    cfg = config or load_config()
    if not allow_broker_calls:
        return {
            "status": "not_run",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "reason": "KIS WebSocket smoke requires allow_broker_calls=True before any credentialed broker call.",
        }
    if cfg.environment == "live" and not allow_live:
        return {
            "status": "blocked",
            "connector": CONNECTOR,
            "profile": cfg.profile,
            "environment": cfg.environment,
            "network": "not_attempted",
            "evidence_path": None,
            "reason": "Live KIS WebSocket smoke requires allow_live=True.",
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
            "reason": "KIS WebSocket smoke evidence_path must be a file path, not a directory.",
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
            "requested_value": str(evidence_target),
            "reason": "KIS WebSocket smoke evidence_path parent directory must be a directory.",
        }

    result = await run_websocket_smoke(
        cfg,
        channel=channel,
        tr_key=tr_key,
        client=client,
        transport=transport,
        max_messages=max_messages,
        message_timeout=message_timeout,
        connect_attempts=connect_attempts,
        connect_backoff_seconds=connect_backoff_seconds,
        reconnect_attempts=reconnect_attempts,
        reconnect_backoff_seconds=reconnect_backoff_seconds,
    )
    written = write_websocket_smoke_evidence(result, evidence_target, max_samples=max_samples)
    evidence = websocket_smoke_evidence(result, max_samples=max_samples)
    evidence["evidence_path"] = str(written)
    return evidence


def _websocket_smoke_evidence_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("type", "status", "prefix", "tr_id", "sequence"):
        if key in sample:
            safe[key] = sample.get(key)
    event = sample.get("event")
    if isinstance(event, Mapping):
        safe["event"] = redact_payload(dict(event))
    for source_key, evidence_key in (
        ("fields", "field_count"),
        ("raw_fields", "raw_field_count"),
        ("raw_values", "raw_value_count"),
    ):
        value = sample.get(source_key)
        if isinstance(value, (Mapping, list, tuple)):
            safe[evidence_key] = len(value)
    return redact_payload(safe)


def parse_websocket_order_notices(message: str | bytes) -> list[dict[str, Any]]:
    """Parse decrypted official KIS ``H0STCNI0``/``H0STCNI9`` order notice frames."""

    raw = message.decode("utf-8") if isinstance(message, bytes) else str(message or "")
    parts = raw.split("|", 3)
    if len(parts) != 4:
        raise KoreanConnectorConfigError("KIS WebSocket order notice parser expected a full data frame.")
    encrypted_flag, tr_id, declared_count_text, payload = parts
    if tr_id not in {"H0STCNI0", "H0STCNI9"}:
        raise KoreanConnectorConfigError(f"KIS WebSocket order notice parser expected H0STCNI0 or H0STCNI9, got {tr_id!r}.")
    try:
        declared_count = int(declared_count_text)
    except ValueError as exc:
        raise KoreanConnectorConfigError("KIS WebSocket order notice parser received an invalid data count.") from exc
    if declared_count < 1:
        raise KoreanConnectorConfigError("KIS WebSocket order notice parser expected at least one notice.")

    values = payload.split("^") if payload else []
    field_count = len(KIS_WEBSOCKET_NOTICE_FIELDS)
    expected_values = declared_count * field_count
    if len(values) != expected_values:
        raise KoreanConnectorConfigError(
            f"KIS WebSocket order notice parser expected {expected_values} values "
            f"({declared_count} x {field_count}), got {len(values)}."
        )

    notices: list[dict[str, Any]] = []
    for index in range(declared_count):
        start = index * field_count
        row_values = values[start : start + field_count]
        fields = {name: row_values[pos] for pos, name in enumerate(KIS_WEBSOCKET_NOTICE_FIELDS)}
        notices.append(_websocket_order_notice(tr_id, fields, row_values, encrypted_flag=encrypted_flag))
    return notices


def decrypt_websocket_payload(cipher_text: str, *, key: str, iv: str) -> str:
    """Decrypt KIS AES256-CBC/Base64 WebSocket notice payloads."""

    clean_key = str(key or "").strip()
    clean_iv = str(iv or "").strip()
    if not clean_key or not clean_iv:
        raise KoreanConnectorConfigError("KIS WebSocket decrypt requires key and iv from the subscription response.")
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError as exc:  # pragma: no cover - exercised only in environments missing declared dependency
        raise KoreanConnectorConfigError("KIS WebSocket decrypt requires the pycryptodome package.") from exc

    try:
        cipher = AES.new(clean_key.encode("utf-8"), AES.MODE_CBC, clean_iv.encode("utf-8"))
        plain = unpad(cipher.decrypt(b64decode(str(cipher_text or ""))), AES.block_size)
        return plain.decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - normalize crypto/base64/padding failures for callers
        raise KoreanConnectorConfigError(f"KIS WebSocket decrypt failed: {exc}") from exc


def parse_websocket_encrypted_order_notices(message: str | bytes, *, key: str, iv: str) -> list[dict[str, Any]]:
    """Decrypt and parse official encrypted KIS order notice frames."""

    raw = message.decode("utf-8") if isinstance(message, bytes) else str(message or "")
    parts = raw.split("|", 3)
    if len(parts) != 4 or parts[0] != "1":
        raise KoreanConnectorConfigError("KIS WebSocket decrypt expected an encrypted order notice frame.")
    encrypted_flag, tr_id, declared_count, cipher_text = parts
    payload = decrypt_websocket_payload(cipher_text, key=key, iv=iv)
    return parse_websocket_order_notices(f"{encrypted_flag}|{tr_id}|{declared_count}|{payload}")


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, client: Any | None = None, **_: Any) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_kr_symbol(symbol)
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": clean}
    tr_id = KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_price"]["tr_id"]
    payload = _request_json(cfg, "GET", "inquire_price", tr_id=tr_id, params=params, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    raw = _first_mapping(payload.get("output"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "quote": {
            "last": _to_float(raw.get("stck_prpr")),
            "change": _to_float(raw.get("prdy_vrss")),
            "change_rate": _to_float(raw.get("prdy_ctrt")),
            "volume": _to_float(raw.get("acml_vol")),
            "turnover": _to_float(raw.get("acml_tr_pbmn")),
            "raw": raw,
        },
    }


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    client: Any | None = None,
    start_date: str = "19000101",
    end_date: str = "29991231",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_kr_symbol(symbol)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": clean,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": _period_code(period),
        "FID_ORG_ADJ_PRC": "0",
    }
    tr_id = KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_daily_itemchartprice"]["tr_id"]
    payload = _request_json(cfg, "GET", "inquire_daily_itemchartprice", tr_id=tr_id, params=params, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    rows = _as_list(payload.get("output2"))[: int(limit)]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "period": period,
        "bars": [_bar_to_dict(item) for item in rows],
        "raw_summary": _first_mapping(payload.get("output1")),
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
    time_in_force: str = "day",
    client: Any | None = None,
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_account_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "KIS orders require quantity; notional-only orders are unsupported."}
    if notional is not None and quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "KIS orders require explicit quantity."}

    clean_side = str(side or "").strip().lower()
    if clean_side not in ("buy", "sell"):
        return {"status": "error", "profile": cfg.profile, "error": "KIS order side must be 'buy' or 'sell'."}

    clean_order_type = str(order_type or "market").strip().lower()
    if clean_order_type == "market":
        ord_dvsn = "01"
        ord_unpr = "0"
    elif clean_order_type == "limit":
        if limit_price is None:
            return {"status": "error", "profile": cfg.profile, "error": "KIS limit orders require limit_price."}
        ord_dvsn = "00"
        ord_unpr = _numeric_string(limit_price)
    else:
        return {"status": "error", "profile": cfg.profile, "error": "KIS order_type must be 'market' or 'limit'."}

    body = {
        "CANO": cfg.account,
        "ACNT_PRDT_CD": cfg.account_product_code,
        "PDNO": _normalize_kr_symbol(symbol),
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": _numeric_string(quantity),
        "ORD_UNPR": ord_unpr,
        "EXCG_ID_DVSN_CD": exchange,
        "SLL_TYPE": "",
        "CNDT_PRIC": "",
    }
    tr_id = _order_cash_tr_id(cfg, clean_side)
    payload = _request_json(cfg, "POST", "order_cash", tr_id=tr_id, body=body, client=client, use_hashkey=True)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["PDNO"])
    output = _first_mapping(payload.get("output"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "paper_guard": "profile_endpoint_separated",
        "symbol": body["PDNO"],
        "side": clean_side,
        "quantity": _to_float(body["ORD_QTY"]),
        "order_type": clean_order_type,
        "order_id": output.get("ODNO") or output.get("odno"),
        "broker_order_ref": output,
        "raw": payload,
    }


def cancel_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    client: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_account_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    try:
        orgno, odno = _split_cancel_order_id(order_id)
    except ValueError as exc:
        return {"status": "error", "profile": cfg.profile, "error": str(exc)}

    body = {
        "CANO": cfg.account,
        "ACNT_PRDT_CD": cfg.account_product_code,
        "KRX_FWDG_ORD_ORGNO": orgno,
        "ORGN_ODNO": odno,
        "ORD_DVSN": "00",
        "RVSE_CNCL_DVSN_CD": "02",
        "ORD_QTY": "0",
        "ORD_UNPR": "0",
        "QTY_ALL_ORD_YN": "Y",
        "EXCG_ID_DVSN_CD": "KRX",
    }
    tr_id = _tr_id("order_rvsecncl", cfg)
    payload = _request_json(cfg, "POST", "order_rvsecncl", tr_id=tr_id, body=body, client=client, use_hashkey=True)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=symbol)
    return {"status": "ok", "profile": cfg.profile, "environment": cfg.environment, "order_id": order_id, "raw": payload}


def _request_json(
    config: KoreanConnectorConfig,
    method: str,
    operation: str,
    *,
    tr_id: str,
    params: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    client: Any | None = None,
    use_hashkey: bool = False,
) -> dict[str, Any]:
    with _client(config, client) as active:
        token = _access_token(config, active)
        headers = _headers(config, token, tr_id)
        if use_hashkey and body is not None:
            headers["hashkey"] = _hashkey(config, active, body)
        url = config.endpoint.rstrip("/") + KIS_DOMESTIC_STOCK_ENDPOINTS[operation]["path"]
        if method == "GET":
            response = active.get(url, params=dict(params or {}), headers=headers, timeout=config.timeout)
        else:
            response = active.post(url, json=dict(body or {}), headers=headers, timeout=config.timeout)
        return _response_json(response)


def _access_token(config: KoreanConnectorConfig, client: Any) -> str:
    if config.access_token:
        return config.access_token
    missing = _missing_auth_fields(config)
    if missing:
        raise KoreanConnectorConfigError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")
    url = config.endpoint.rstrip("/") + KIS_DOMESTIC_STOCK_ENDPOINTS["auth_token"]["path"]
    response = client.post(
        url,
        json={"grant_type": "client_credentials", "appkey": config.app_key, "appsecret": config.app_secret},
        headers={"content-type": "application/json"},
        timeout=config.timeout,
    )
    payload = _response_json(response)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise KoreanConnectorConfigError(f"{LABEL} auth token response missing access_token.")
    return token


def _hashkey(config: KoreanConnectorConfig, client: Any, body: Mapping[str, Any]) -> str:
    url = config.endpoint.rstrip("/") + KIS_DOMESTIC_STOCK_ENDPOINTS["hashkey"]["path"]
    response = client.post(
        url,
        json=dict(body),
        headers={"content-type": "application/json", "appkey": config.app_key, "appsecret": config.app_secret},
        timeout=config.timeout,
    )
    payload = _response_json(response)
    value = str(payload.get("HASH") or payload.get("hash") or "").strip()
    if not value:
        raise KoreanConnectorConfigError(f"{LABEL} hashkey response missing HASH.")
    return value


def _headers(config: KoreanConnectorConfig, token: str, tr_id: str) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": config.app_key,
        "appsecret": config.app_secret,
        "tr_id": tr_id,
        "custtype": "P",
    }


@contextmanager
def _client(config: KoreanConnectorConfig, client: Any | None = None) -> Iterator[Any]:
    if client is not None:
        yield client
        return
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise KoreanConnectorConfigError("KIS REST calls require httpx; install project dependencies first.") from exc
    with httpx.Client(timeout=config.timeout, follow_redirects=True, trust_env=True) as active:
        yield active


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    payload = response.json()
    return dict(payload or {}) if isinstance(payload, Mapping) else {"raw": payload}


def _payload_ok(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("rt_cd", "0")) == "0"


def _error_payload(config: KoreanConnectorConfig, payload: Mapping[str, Any], *, symbol: str | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "environment": config.environment,
        "symbol": symbol,
        "error": str(payload.get("msg1") or payload.get("error_description") or payload.get("error") or "KIS API error"),
        "code": payload.get("msg_cd") or payload.get("error_code"),
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


def _missing_account_fields(config: KoreanConnectorConfig) -> list[str]:
    missing = _missing_auth_fields(config)
    if not config.account:
        missing.append("account")
    if not config.account_product_code:
        missing.append("account_product_code")
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


def _period_code(period: str) -> str:
    return _PERIOD_MAP.get(str(period or "1d").strip(), "D")


def _tr_id(operation: str, config: KoreanConnectorConfig) -> str:
    item = KIS_DOMESTIC_STOCK_ENDPOINTS[operation]
    return item["paper_tr_id"] if config.environment == "paper" else item["live_tr_id"]


def _order_cash_tr_id(config: KoreanConnectorConfig, side: str) -> str:
    env = "paper" if config.environment == "paper" else "live"
    return KIS_DOMESTIC_STOCK_ENDPOINTS["order_cash"][f"{env}_{side}_tr_id"]


def _websocket_channel(channel: str) -> dict[str, str]:
    spec = KIS_WEBSOCKET_CHANNELS.get(str(channel or "").strip().lower())
    if spec is None:
        raise KoreanConnectorConfigError(f"unsupported KIS WebSocket channel: {channel!r}")
    return spec


def _websocket_tr_id(spec: Mapping[str, str], config: KoreanConnectorConfig) -> str:
    if "paper_tr_id" in spec or "live_tr_id" in spec:
        return spec["paper_tr_id"] if config.environment == "paper" else spec["live_tr_id"]
    return spec["tr_id"]


def _websocket_columns_for_channel(channel: str) -> list[str]:
    spec = _websocket_channel(channel)
    for key in ("tr_id", "paper_tr_id", "live_tr_id"):
        tr_id = spec.get(key)
        if tr_id and tr_id in KIS_WEBSOCKET_COLUMNS:
            return KIS_WEBSOCKET_COLUMNS[tr_id]
    return []


def _websocket_kind_for_tr_id(tr_id: str) -> str:
    for spec in KIS_WEBSOCKET_CHANNELS.values():
        if tr_id in {spec.get("tr_id"), spec.get("paper_tr_id"), spec.get("live_tr_id")}:
            return spec.get("kind", "")
    return ""


def _websocket_event(tr_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    kind = _websocket_kind_for_tr_id(tr_id)
    if kind in {"trade", "expected_trade", "overtime_trade"}:
        return {
            "kind": kind,
            "symbol": fields.get("MKSC_SHRN_ISCD"),
            "time": fields.get("STCK_CNTG_HOUR"),
            "last": _to_float(fields.get("STCK_PRPR")),
            "change": _to_float(fields.get("PRDY_VRSS")),
            "change_rate": _to_float(fields.get("PRDY_CTRT")),
            "trade_volume": _to_float(fields.get("CNTG_VOL")),
            "volume": _to_float(fields.get("ACML_VOL")),
            "ask": _to_float(fields.get("ASKP1")),
            "bid": _to_float(fields.get("BIDP1")),
        }
    if kind == "orderbook":
        return {
            "kind": kind,
            "symbol": fields.get("MKSC_SHRN_ISCD"),
            "time": fields.get("BSOP_HOUR"),
            "asks": _websocket_book_side(fields, "ASKP", "ASKP_RSQN"),
            "bids": _websocket_book_side(fields, "BIDP", "BIDP_RSQN"),
        }
    if kind == "order_notice":
        return {
            "kind": kind,
            "account": fields.get("ACNT_NO"),
            "order_id": fields.get("ODER_NO"),
            "original_order_id": fields.get("OODER_NO"),
            "symbol": fields.get("STCK_SHRN_ISCD"),
            "execution_quantity": _to_float(fields.get("CNTG_QTY")),
            "execution_price": _to_float(fields.get("CNTG_UNPR")),
            "execution_time": fields.get("STCK_CNTG_HOUR"),
            "execution_notice": fields.get("CNTG_YN") == "2",
            "accepted": fields.get("ACPT_YN"),
            "exchange": fields.get("ORD_EXG_GB"),
        }
    return {"kind": kind or "raw"}


def _websocket_trade_tick(fields: Mapping[str, Any], raw_values: list[str]) -> dict[str, Any]:
    return {
        "kind": "trade",
        "symbol": fields.get("MKSC_SHRN_ISCD"),
        "time": fields.get("STCK_CNTG_HOUR"),
        "last": _to_float(fields.get("STCK_PRPR")),
        "change_sign": fields.get("PRDY_VRSS_SIGN"),
        "change": _to_float(fields.get("PRDY_VRSS")),
        "change_rate": _to_float(fields.get("PRDY_CTRT")),
        "weighted_average_price": _to_float(fields.get("WGHN_AVRG_STCK_PRC")),
        "open": _to_float(fields.get("STCK_OPRC")),
        "high": _to_float(fields.get("STCK_HGPR")),
        "low": _to_float(fields.get("STCK_LWPR")),
        "ask": _to_float(fields.get("ASKP1")),
        "bid": _to_float(fields.get("BIDP1")),
        "trade_volume": _to_float(fields.get("CNTG_VOL")),
        "signed_trade_volume": _kis_signed_trade_volume(fields),
        "cumulative_volume": _to_float(fields.get("ACML_VOL")),
        "cumulative_trade_value": _to_float(fields.get("ACML_TR_PBMN")),
        "sell_execution_count": _to_float(fields.get("SELN_CNTG_CSNU")),
        "buy_execution_count": _to_float(fields.get("SHNU_CNTG_CSNU")),
        "net_buy_execution_count": _to_float(fields.get("NTBY_CNTG_CSNU")),
        "trade_strength": _to_float(fields.get("CTTR")),
        "sell_execution_quantity_total": _to_float(fields.get("SELN_CNTG_SMTN")),
        "buy_execution_quantity_total": _to_float(fields.get("SHNU_CNTG_SMTN")),
        "execution_side": fields.get("CCLD_DVSN"),
        "buy_ratio": _to_float(fields.get("SHNU_RATE")),
        "previous_volume_rate": _to_float(fields.get("PRDY_VOL_VRSS_ACML_VOL_RATE")),
        "open_time": fields.get("OPRC_HOUR"),
        "open_change_sign": fields.get("OPRC_VRSS_PRPR_SIGN"),
        "open_change": _to_float(fields.get("OPRC_VRSS_PRPR")),
        "high_time": fields.get("HGPR_HOUR"),
        "high_change_sign": fields.get("HGPR_VRSS_PRPR_SIGN"),
        "high_change": _to_float(fields.get("HGPR_VRSS_PRPR")),
        "low_time": fields.get("LWPR_HOUR"),
        "low_change_sign": fields.get("LWPR_VRSS_PRPR_SIGN"),
        "low_change": _to_float(fields.get("LWPR_VRSS_PRPR")),
        "business_date": fields.get("BSOP_DATE"),
        "new_market_operation_code": fields.get("NEW_MKOP_CLS_CODE"),
        "trading_halt": _yn_bool(fields.get("TRHT_YN")),
        "ask_quantity": _to_float(fields.get("ASKP_RSQN1")),
        "bid_quantity": _to_float(fields.get("BIDP_RSQN1")),
        "total_ask_quantity": _to_float(fields.get("TOTAL_ASKP_RSQN")),
        "total_bid_quantity": _to_float(fields.get("TOTAL_BIDP_RSQN")),
        "volume_turnover": _to_float(fields.get("VOL_TNRT")),
        "previous_same_time_cumulative_volume": _to_float(fields.get("PRDY_SMNS_HOUR_ACML_VOL")),
        "previous_same_time_cumulative_volume_rate": _to_float(fields.get("PRDY_SMNS_HOUR_ACML_VOL_RATE")),
        "hour_class_code": fields.get("HOUR_CLS_CODE"),
        "market_treatment_class_code": fields.get("MRKT_TRTM_CLS_CODE"),
        "vi_standard_price": _to_float(fields.get("VI_STND_PRC")),
        "raw_fields": dict(fields),
        "raw_values": list(raw_values),
    }


def _kis_signed_trade_volume(fields: Mapping[str, Any]) -> float | None:
    volume = _to_float(fields.get("CNTG_VOL"))
    if volume is None:
        return None
    execution_side = str(fields.get("CCLD_DVSN") or "").strip()
    if execution_side == "5":
        return -abs(volume)
    if execution_side == "1":
        return abs(volume)
    return volume


def _websocket_book_side(fields: Mapping[str, Any], price_prefix: str, quantity_prefix: str) -> list[dict[str, float | int]]:
    levels: list[dict[str, float | int]] = []
    for index in range(1, 11):
        price = _to_float(fields.get(f"{price_prefix}{index}"))
        quantity = _to_float(fields.get(f"{quantity_prefix}{index}"))
        if price is not None or quantity is not None:
            levels.append({"level": index, "price": price, "quantity": quantity})
    return levels


def _websocket_orderbook(fields: Mapping[str, Any], raw_values: list[str]) -> dict[str, Any]:
    return {
        "kind": "orderbook",
        "symbol": fields.get("MKSC_SHRN_ISCD"),
        "time": fields.get("BSOP_HOUR"),
        "hour_class_code": fields.get("HOUR_CLS_CODE"),
        "asks": _websocket_book_side(fields, "ASKP", "ASKP_RSQN"),
        "bids": _websocket_book_side(fields, "BIDP", "BIDP_RSQN"),
        "total_ask_quantity": _to_float(fields.get("TOTAL_ASKP_RSQN")),
        "total_bid_quantity": _to_float(fields.get("TOTAL_BIDP_RSQN")),
        "overtime_total_ask_quantity": _to_float(fields.get("OVTM_TOTAL_ASKP_RSQN")),
        "overtime_total_bid_quantity": _to_float(fields.get("OVTM_TOTAL_BIDP_RSQN")),
        "anticipated_price": _to_float(fields.get("ANTC_CNPR")),
        "anticipated_quantity": _to_float(fields.get("ANTC_CNQN")),
        "anticipated_volume": _to_float(fields.get("ANTC_VOL")),
        "anticipated_change": _to_float(fields.get("ANTC_CNTG_VRSS")),
        "anticipated_change_sign": fields.get("ANTC_CNTG_VRSS_SIGN"),
        "anticipated_change_rate": _to_float(fields.get("ANTC_CNTG_PRDY_CTRT")),
        "cumulative_volume": _to_float(fields.get("ACML_VOL")),
        "total_ask_quantity_change": _to_float(fields.get("TOTAL_ASKP_RSQN_ICDC")),
        "total_bid_quantity_change": _to_float(fields.get("TOTAL_BIDP_RSQN_ICDC")),
        "overtime_total_ask_change": _to_float(fields.get("OVTM_TOTAL_ASKP_ICDC")),
        "overtime_total_bid_change": _to_float(fields.get("OVTM_TOTAL_BIDP_ICDC")),
        "stock_deal_class_code": fields.get("STCK_DEAL_CLS_CODE"),
        "raw_fields": dict(fields),
        "raw_values": list(raw_values),
    }


def _websocket_order_notice(
    tr_id: str,
    fields: Mapping[str, Any],
    raw_values: list[str],
    *,
    encrypted_flag: str,
) -> dict[str, Any]:
    cntg_yn = str(fields.get("CNTG_YN") or "").strip()
    return {
        "kind": "order_notice",
        "tr_id": tr_id,
        "environment": "paper" if tr_id == "H0STCNI9" else "live",
        "encrypted": str(encrypted_flag).strip() == "1",
        "customer_id": fields.get("CUST_ID"),
        "account": fields.get("ACNT_NO"),
        "order_id": fields.get("ODER_NO"),
        "original_order_id": fields.get("OODER_NO"),
        "side": _kis_order_side(fields.get("SELN_BYOV_CLS")),
        "receipt_class": fields.get("RCTF_CLS"),
        "order_kind": fields.get("ODER_KIND"),
        "order_condition": fields.get("ODER_COND"),
        "symbol": fields.get("STCK_SHRN_ISCD"),
        "execution_quantity": _to_float(fields.get("CNTG_QTY")),
        "execution_price": _to_float(fields.get("CNTG_UNPR")),
        "execution_time": fields.get("STCK_CNTG_HOUR"),
        "refused": _yn_bool(fields.get("RFUS_YN")),
        "notice_type": "execution" if cntg_yn == "2" else "order_status" if cntg_yn == "1" else "raw",
        "execution_notice": cntg_yn == "2",
        "accepted": _yn_bool(fields.get("ACPT_YN")),
        "branch_no": fields.get("BRNC_NO"),
        "order_quantity": _to_float(fields.get("ODER_QTY")),
        "account_name": fields.get("ACNT_NAME"),
        "order_condition_price": _to_float(fields.get("ORD_COND_PRC")),
        "exchange": fields.get("ORD_EXG_GB"),
        "popup": _yn_bool(fields.get("POPUP_YN")),
        "credit_class": fields.get("CRDT_CLS"),
        "credit_loan_date": fields.get("CRDT_LOAN_DATE"),
        "execution_date": fields.get("CNTG_ISNM40"),
        "order_price": _to_float(fields.get("ODER_PRC")),
        "raw_fields": dict(fields),
        "raw_values": list(raw_values),
    }


def _account_ref(config: KoreanConnectorConfig) -> str:
    if not config.account:
        return ""
    return f"{config.account[:2]}***{config.account[-2:]}-{config.account_product_code}"


def _position_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(item.get("pdno") or item.get("PDNO") or "").strip(),
        "quantity": _to_float(item.get("hldg_qty")),
        "market_value": _to_float(item.get("evlu_amt")),
        "average_price": _to_float(item.get("pchs_avg_pric")),
        "raw": dict(item),
    }


def _open_order_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    order_id = str(_field(item, "odno", "ODNO", "orgn_odno", "ORGN_ODNO") or "").strip()
    orgno = str(
        _field(item, "ord_gno_brno", "ORD_GNO_BRNO", "krx_fwdg_ord_orgno", "KRX_FWDG_ORD_ORGNO") or ""
    ).strip()
    quantity = _to_float(_field(item, "ord_qty", "ORD_QTY"))
    filled_quantity = _to_float(_field(item, "tot_ccld_qty", "TOT_CCLD_QTY", "ccld_qty", "CCLD_QTY"))
    cancelable_quantity = _to_float(_field(item, "psbl_qty", "PSBL_QTY"))
    remaining_quantity = cancelable_quantity
    if remaining_quantity is None and quantity is not None and filled_quantity is not None:
        remaining_quantity = max(quantity - filled_quantity, 0.0)
    return {
        "order_id": order_id,
        "broker_order_id": f"{orgno}:{order_id}" if orgno and order_id else order_id,
        "symbol": str(_field(item, "pdno", "PDNO", "stck_shrn_iscd", "STCK_SHRN_ISCD") or "").strip(),
        "side": _kis_order_side(_field(item, "sll_buy_dvsn_cd", "SLL_BUY_DVSN_CD", "sll_buy_dvsn_name")),
        "quantity": quantity,
        "filled_quantity": filled_quantity,
        "remaining_quantity": remaining_quantity,
        "cancelable_quantity": cancelable_quantity,
        "limit_price": _to_float(_field(item, "ord_unpr", "ORD_UNPR")),
        "raw": dict(item),
    }


def _bar_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "date": item.get("stck_bsop_date"),
        "open": _to_float(item.get("stck_oprc")),
        "high": _to_float(item.get("stck_hgpr")),
        "low": _to_float(item.get("stck_lwpr")),
        "close": _to_float(item.get("stck_clpr")),
        "volume": _to_float(item.get("acml_vol")),
        "raw": dict(item),
    }


def _as_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def _first_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list) and value and isinstance(value[0], Mapping):
        return dict(value[0])
    return {}


def _field(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return None


def _kis_order_side(value: Any) -> str | None:
    token = str(value or "").strip().lower()
    return {
        "01": "sell",
        "1": "sell",
        "sell": "sell",
        "매도": "sell",
        "02": "buy",
        "2": "buy",
        "buy": "buy",
        "매수": "buy",
    }.get(token, token or None)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _yn_bool(value: Any) -> bool | None:
    token = str(value or "").strip().upper()
    if token == "Y":
        return True
    if token == "N":
        return False
    return None


def _numeric_string(value: float | int | str) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)


def _split_cancel_order_id(order_id: str) -> tuple[str, str]:
    token = str(order_id or "").strip()
    if ":" not in token:
        raise ValueError("KIS cancel_order requires order_id as 'KRX_FWDG_ORD_ORGNO:ORGN_ODNO'.")
    orgno, odno = [part.strip() for part in token.split(":", 1)]
    if not orgno or not odno:
        raise ValueError("KIS cancel_order requires both KRX_FWDG_ORD_ORGNO and ORGN_ODNO.")
    return orgno, odno
