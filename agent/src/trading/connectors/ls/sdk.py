"""LS Securities OpenAPI connector.

The REST catalog here is limited to LS Securities' official OpenAPI sample and
guide JSON surface verified for this port: token issuance, t1101 stock quote,
t0424 account balance, and CSPAT00601/CSPAT00701/CSPAT00801 stock order flows.
The WebSocket catalog is derived from the official ``[주식] 실시간 시세``
guide JSON for `/websocket/stock`.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from src.config.paths import get_runtime_root
from src.trading.connectors.kr_common import (
    KoreanConnectorConfig,
    KoreanConnectorConfigError,
    build_config as _build_config,
    check_status as _check_status,
    load_config as _load_config,
    save_config as _save_config,
    unsupported_or_unconfigured,
)

CONFIG_FILENAME = "ls.json"
PAPER_URL = "https://openapi.ls-sec.co.kr:8080"
LIVE_URL = "https://openapi.ls-sec.co.kr:8080"
LABEL = "LS OpenAPI"
CONNECTOR = "ls"

LS_OPENAPI_ENDPOINTS: dict[str, dict[str, str]] = {
    "auth_token": {
        "method": "POST",
        "path": "/oauth2/token",
        "content_type": "application/x-www-form-urlencoded",
    },
    "stock_quote": {
        "method": "POST",
        "path": "/stock/market-data",
        "tr_cd": "t1101",
    },
    "account_balance": {
        "method": "POST",
        "path": "/stock/accno",
        "tr_cd": "t0424",
    },
    "stock_order": {
        "method": "POST",
        "path": "/stock/order",
        "tr_cd": "CSPAT00601",
    },
    "modify_order": {
        "method": "POST",
        "path": "/stock/order",
        "tr_cd": "CSPAT00701",
    },
    "cancel_order": {
        "method": "POST",
        "path": "/stock/order",
        "tr_cd": "CSPAT00801",
    },
}

LS_WEBSOCKET_URLS: dict[str, str] = {
    "paper": "wss://openapi.ls-sec.co.kr:29443",
    "live": "wss://openapi.ls-sec.co.kr:9443",
}

LS_WEBSOCKET_ENDPOINTS: dict[str, dict[str, str]] = {
    "stock_realtime": {
        "api_id": "9a2800c3-9bf2-4d67-8d83-905074f06646",
        "path": "/websocket/stock",
        "protocol": "WEBSOCKET",
        "content_type": "application/json; charset=UTF-8",
    },
}

LS_STOCK_WEBSOCKET_TRS: dict[str, str] = {
    "B7_": "ETF호가잔량",
    "DH1": "KOSPI시간외단일가호가잔량",
    "DHA": "KOSDAQ시간외단일가호가잔량",
    "DK3": "KOSDAQ시간외단일가체결",
    "DS3": "KOSPI시간외단일가체결",
    "DVI": "시간외단일가VI발동해제",
    "H1_": "KOSPI호가잔량",
    "H2_": "KOSPI장전시간외호가잔량",
    "HA_": "KOSDAQ호가잔량",
    "HB_": "KOSDAQ장전시간외호가잔량",
    "I5_": "코스피ETF종목실시간NAV",
    "IJ_": "지수",
    "K1_": "KOSPI거래원",
    "K3_": "KOSDAQ체결",
    "KH_": "KOSDAQ프로그램매매종목별",
    "KM_": "KOSDAQ프로그램매매전체집계",
    "KS_": "KOSDAQ우선호가",
    "OK_": "KOSDAQ거래원",
    "PH_": "KOSPI프로그램매매종목별",
    "PM_": "KOSPI프로그램매매전체집계",
    "S2_": "KOSPI우선호가",
    "S3_": "KOSPI체결",
    "S4_": "KOSPI기세",
    "SC0": "주식주문접수",
    "SC1": "주식주문체결",
    "SC2": "주식주문정정",
    "SC3": "주식주문취소",
    "SC4": "주식주문거부",
    "SHC": "상/하한가근접진입",
    "SHD": "상/하한가근접이탈",
    "SHI": "상/하한가진입",
    "SHO": "상/하한가이탈",
    "VI_": "VI발동해제",
    "YJ_": "예상지수",
    "YK3": "KOSDAQ예상체결",
    "YS3": "KOSPI예상체결",
    "ESN": "뉴ELW투자지표민감도",
    "h2_": "ELW장전시간외호가잔량",
    "h3_": "ELW호가잔량",
    "k1_": "ELW거래원",
    "s2_": "ELW우선호가",
    "s3_": "ELW체결",
    "s4_": "ELW기세",
    "Ys3": "ELW예상체결",
    "NS3": "(NXT)체결",
    "NH1": "(NXT)호가잔량",
    "NS2": "(NXT)우선호가",
    "NYS": "(NXT)예상체결",
    "NVI": "(NXT)VI 발동 해제",
    "NK1": "(NXT)거래원",
    "NPH": "(NXT)프로그램매매종목별",
    "NPM": "(NXT)프로그램매매전체집계",
    "NBT": "(NXT)시간대별투자자매매추이",
    "NBM": "(NXT)업종별투자자별매매현황",
    "US3": "(통합)체결",
    "UH1": "(통합)호가잔량",
    "US2": "(통합)우선호가",
    "UYS": "(통합)예상체결",
    "UPH": "(통합)프로그램매매종목별",
    "UK1": "(통합)거래원",
    "UBT": "(통합)시간대별투자자매매추이",
    "UBM": "(통합) 업종별투자자별매매현황",
    "UPM": "(통합)프로그램매매전체집계",
    "UVI": "(통합)VI발동해제",
    "AFR": "API사용자조건검색실시간",
}

LS_WEBSOCKET_CHANNELS: dict[str, dict[str, str]] = {
    "kospi_trade": {"tr_cd": "S3_", "tr_type": "3", "kind": "trade", "tr_key": "symbol"},
    "kosdaq_trade": {"tr_cd": "K3_", "tr_type": "3", "kind": "trade", "tr_key": "symbol"},
    "nxt_trade": {"tr_cd": "NS3", "tr_type": "3", "kind": "trade", "tr_key": "symbol"},
    "total_trade": {"tr_cd": "US3", "tr_type": "3", "kind": "trade", "tr_key": "symbol"},
    "kospi_orderbook": {"tr_cd": "H1_", "tr_type": "3", "kind": "orderbook", "tr_key": "symbol"},
    "kosdaq_orderbook": {"tr_cd": "HA_", "tr_type": "3", "kind": "orderbook", "tr_key": "symbol"},
    "nxt_orderbook": {"tr_cd": "NH1", "tr_type": "3", "kind": "orderbook", "tr_key": "symbol"},
    "total_orderbook": {"tr_cd": "UH1", "tr_type": "3", "kind": "orderbook", "tr_key": "symbol"},
    "stock_order_accept": {"tr_cd": "SC0", "tr_type": "1", "kind": "order_accept", "tr_key": "account"},
    "stock_order_execution": {"tr_cd": "SC1", "tr_type": "1", "kind": "order_execution", "tr_key": "account"},
    "stock_order_modify": {"tr_cd": "SC2", "tr_type": "1", "kind": "order_modify", "tr_key": "account"},
    "stock_order_cancel": {"tr_cd": "SC3", "tr_type": "1", "kind": "order_cancel", "tr_key": "account"},
    "stock_order_reject": {"tr_cd": "SC4", "tr_type": "1", "kind": "order_reject", "tr_key": "account"},
}

_ORDER_SUCCESS_CODES = {"stock_order": {"00040"}, "modify_order": {"00000"}, "cancel_order": {"00156"}}


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
    report["auth_probe_reason"] = "LS token issuance is deferred until an explicit read/order call."
    report["official_catalog"] = "token,t1101,t0424,CSPAT00601,CSPAT00701,CSPAT00801,stock-websocket-65tr"
    return report


def get_account_snapshot(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    body = {"t0424InBlock": {"prcgb": "", "chegb": "", "dangb": "", "charge": "", "cts_expcode": ""}}
    payload = _request_json(cfg, "account_balance", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)

    raw_account = _first_mapping(payload.get("t0424OutBlock"))
    positions = [_position_to_dict(item) for item in _as_list(payload.get("t0424OutBlock1"))]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "account": {
            "cash": _to_float(raw_account.get("sunamt")),
            "total_value": _to_float(raw_account.get("tappamt")),
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


def get_open_orders(config: KoreanConnectorConfig | None = None, *, include_executions: bool = False) -> dict[str, Any]:
    return unsupported_or_unconfigured(config or load_config(), label=LABEL, operation="open orders")


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, client: Any | None = None, **_: Any) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_kr_symbol(symbol)
    payload = _request_json(cfg, "stock_quote", body={"t1101InBlock": {"shcode": clean}}, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    raw = _first_mapping(payload.get("t1101OutBlock"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "quote": {
            "last": _to_float(raw.get("price")),
            "change": _to_float(raw.get("change")),
            "change_rate": _to_float(raw.get("diff")),
            "volume": _to_float(raw.get("volume")),
            "raw": raw,
        },
    }


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    return {
        "status": "error",
        "profile": cfg.profile,
        "error": "LS historical bars are not implemented yet; t1301 is an intraday execution feed, not an OHLC bar contract.",
    }


def websocket_url(config: KoreanConnectorConfig | None = None) -> str:
    """Return LS OpenAPI's official stock WebSocket endpoint for the active profile."""

    cfg = config or load_config()
    base = LS_WEBSOCKET_URLS["paper"] if cfg.environment == "paper" else LS_WEBSOCKET_URLS["live"]
    return base + LS_WEBSOCKET_ENDPOINTS["stock_realtime"]["path"]


def build_websocket_subscribe_message(
    tr_key: str,
    *,
    channel: str,
    config: KoreanConnectorConfig | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Build the official LS OpenAPI WebSocket subscription frame."""

    cfg = config or load_config()
    spec = LS_WEBSOCKET_CHANNELS.get(str(channel or "").strip().lower())
    if spec is None:
        raise KoreanConnectorConfigError(f"unsupported LS WebSocket channel: {channel!r}")
    token = cfg.access_token
    if not token:
        if client is None:
            raise KoreanConnectorConfigError("LS WebSocket subscriptions require access_token or a client for token issuance.")
        token = _access_token(cfg, client)

    key = str(tr_key or "").strip()
    if spec.get("tr_key") == "symbol":
        key = _normalize_kr_symbol(key)
        if not key:
            raise KoreanConnectorConfigError(f"LS WebSocket channel {channel!r} requires a symbol.")

    return {
        "header": {"token": token, "tr_type": spec["tr_type"]},
        "body": {"tr_cd": spec["tr_cd"], "tr_key": key},
    }


def parse_websocket_message(message: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    """Normalize LS WebSocket JSON events into stable dictionaries."""

    if isinstance(message, bytes):
        message = message.decode("utf-8")
    payload = json.loads(message) if isinstance(message, str) else dict(message)
    header = _first_mapping(payload.get("header"))
    body = _first_mapping(payload.get("body"))
    tr_cd = str(header.get("tr_cd") or body.get("tr_cd") or "").strip()
    kind = _websocket_kind(tr_cd)

    if kind == "trade":
        symbol = _normalize_kr_symbol(str(body.get("shcode") or header.get("tr_key") or ""))
        return {
            "status": "ok",
            "channel": "trade",
            "tr_cd": tr_cd,
            "symbol": symbol,
            "quote": {
                "last": _to_float(body.get("price") or body.get("dan_price")),
                "change": _to_float(body.get("change") or body.get("dan_change")),
                "change_rate": _to_float(body.get("drate") or body.get("dan_drate")),
                "trade_volume": _to_float(body.get("cvolume") or body.get("dan_cvolume")),
                "volume": _to_float(body.get("volume") or body.get("dan_volume")),
                "time": str(body.get("chetime") or body.get("dan_chetime") or "").strip(),
                "raw": body,
            },
            "raw": payload,
        }

    if kind == "orderbook":
        symbol = _normalize_kr_symbol(str(body.get("shcode") or header.get("tr_key") or ""))
        return {
            "status": "ok",
            "channel": "orderbook",
            "tr_cd": tr_cd,
            "symbol": symbol,
            "orderbook": {
                "asks": _price_levels(body, price_prefix="offerho", qty_prefix="offerrem"),
                "bids": _price_levels(body, price_prefix="bidho", qty_prefix="bidrem"),
                "time": str(body.get("hotime") or body.get("dan_hotime") or "").strip(),
                "raw": body,
            },
            "raw": payload,
        }

    if kind.startswith("order_"):
        return {
            "status": "ok",
            "channel": kind,
            "tr_cd": tr_cd,
            "order": {
                "account": str(body.get("accno") or body.get("ordacntno") or "").strip(),
                "symbol": _normalize_kr_symbol(str(body.get("shtnIsuno") or body.get("Isuno") or "")),
                "order_id": str(body.get("ordno") or "").strip(),
                "original_order_id": str(body.get("orgordno") or "").strip(),
                "side": _order_side_from_code(body.get("bnstp")),
                "order_quantity": _to_float(body.get("ordqty")),
                "filled_quantity": _to_float(body.get("execqty")),
                "remaining_quantity": _to_float(body.get("unercqty")),
                "order_price": _to_float(body.get("ordprc")),
                "executed_price": _to_float(body.get("execprc")),
                "raw": body,
            },
            "raw": payload,
        }

    return {
        "status": "ok",
        "channel": kind or tr_cd.lower() or "unknown",
        "tr_cd": tr_cd,
        "raw": payload,
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
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "LS orders require quantity; notional-only orders are unsupported."}
    if notional is not None and quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "LS orders require explicit quantity."}

    clean_side = str(side or "").strip().lower()
    if clean_side not in ("buy", "sell"):
        return {"status": "error", "profile": cfg.profile, "error": "LS order side must be 'buy' or 'sell'."}
    bns_tp_code = "2" if clean_side == "buy" else "1"

    clean_type = str(order_type or "market").strip().lower()
    if clean_type == "limit":
        if limit_price is None:
            return {"status": "error", "profile": cfg.profile, "error": "LS limit orders require limit_price."}
        ordprc_ptn_code = "00"
        ord_prc = _numeric_value(limit_price)
    elif clean_type == "market":
        ordprc_ptn_code = "03"
        ord_prc = 0
    else:
        return {"status": "error", "profile": cfg.profile, "error": "LS order_type must be 'market' or 'limit'."}

    body = {
        "CSPAT00601InBlock1": {
            "IsuNo": _order_symbol(symbol),
            "OrdQty": _numeric_value(quantity),
            "OrdPrc": ord_prc,
            "BnsTpCode": bns_tp_code,
            "OrdprcPtnCode": ordprc_ptn_code,
            "MgntrnCode": "000",
            "LoanDt": "",
            "OrdCndiTpCode": _order_condition_code(time_in_force),
            "MbrNo": (str(exchange or "KRX").strip().upper() or "KRX"),
        }
    }
    payload = _request_json(cfg, "stock_order", body=body, client=client)
    if not _payload_ok(payload, operation="stock_order"):
        return _error_payload(cfg, payload, symbol=body["CSPAT00601InBlock1"]["IsuNo"])
    output = _first_mapping(payload.get("CSPAT00601OutBlock2"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "paper_guard": "profile_endpoint_separated",
        "symbol": body["CSPAT00601InBlock1"]["IsuNo"],
        "side": clean_side,
        "quantity": _to_float(body["CSPAT00601InBlock1"]["OrdQty"]),
        "order_type": clean_type,
        "order_id": str(output.get("OrdNo") or ""),
        "broker_order_ref": output,
        "raw": payload,
    }


def cancel_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    quantity: float | int | str | None = None,
    client: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "LS cancel_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "LS cancel_order requires symbol."}
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "LS cancel_order requires quantity because CSPAT00801 requires OrdQty."}

    body = {
        "CSPAT00801InBlock1": {
            "OrgOrdNo": _numeric_value(order_id),
            "IsuNo": _order_symbol(symbol),
            "OrdQty": _numeric_value(quantity),
        }
    }
    payload = _request_json(cfg, "cancel_order", body=body, client=client)
    if not _payload_ok(payload, operation="cancel_order"):
        return _error_payload(cfg, payload, symbol=body["CSPAT00801InBlock1"]["IsuNo"])
    return {"status": "ok", "profile": cfg.profile, "environment": cfg.environment, "order_id": str(order_id), "raw": payload}


def modify_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    quantity: float | int | str | None = None,
    limit_price: float | int | str | None = None,
    time_in_force: str = "day",
    client: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "LS modify_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "LS modify_order requires symbol."}
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "LS modify_order requires quantity."}
    if limit_price is None:
        return {"status": "error", "profile": cfg.profile, "error": "LS modify_order requires limit_price."}

    body = {
        "CSPAT00701InBlock1": {
            "OrgOrdNo": _numeric_value(order_id),
            "IsuNo": _order_symbol(symbol),
            "OrdQty": _numeric_value(quantity),
            "OrdprcPtnCode": "00",
            "OrdCndiTpCode": _order_condition_code(time_in_force),
            "OrdPrc": _numeric_value(limit_price),
        }
    }
    payload = _request_json(cfg, "modify_order", body=body, client=client)
    if not _payload_ok(payload, operation="modify_order"):
        return _error_payload(cfg, payload, symbol=body["CSPAT00701InBlock1"]["IsuNo"])
    output = _first_mapping(payload.get("CSPAT00701OutBlock2"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "order_id": str(order_id),
        "broker_order_ref": output,
        "raw": payload,
    }


def _request_json(
    config: KoreanConnectorConfig,
    operation: str,
    *,
    body: Mapping[str, Any],
    client: Any | None = None,
) -> dict[str, Any]:
    with _client(config, client) as active:
        token = _access_token(config, active)
        endpoint = LS_OPENAPI_ENDPOINTS[operation]
        url = config.endpoint.rstrip("/") + endpoint["path"]
        response = active.post(
            url,
            json=dict(body),
            headers=_headers(token, endpoint["tr_cd"]),
            timeout=config.timeout,
        )
        return _response_json(response)


def _access_token(config: KoreanConnectorConfig, client: Any) -> str:
    if config.access_token:
        return config.access_token
    missing = _missing_auth_fields(config)
    if missing:
        raise KoreanConnectorConfigError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")
    url = config.endpoint.rstrip("/") + LS_OPENAPI_ENDPOINTS["auth_token"]["path"]
    response = client.post(
        url,
        params={"grant_type": "client_credentials", "appkey": config.app_key, "appsecretkey": config.app_secret, "scope": "oob"},
        headers={"content-type": LS_OPENAPI_ENDPOINTS["auth_token"]["content_type"]},
        timeout=config.timeout,
    )
    payload = _response_json(response)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise KoreanConnectorConfigError(f"{LABEL} auth token response missing access_token.")
    return token


def _headers(token: str, tr_cd: str) -> dict[str, str]:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "tr_cd": tr_cd,
        "tr_cont": "N",
        "tr_cont_key": "",
    }


@contextmanager
def _client(config: KoreanConnectorConfig, client: Any | None = None) -> Iterator[Any]:
    if client is not None:
        yield client
        return
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise KoreanConnectorConfigError("LS REST calls require httpx; install project dependencies first.") from exc
    with httpx.Client(timeout=config.timeout, follow_redirects=True, trust_env=True) as active:
        yield active


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    payload = response.json()
    return dict(payload or {}) if isinstance(payload, Mapping) else {"raw": payload}


def _payload_ok(payload: Mapping[str, Any], *, operation: str = "") -> bool:
    code = str(payload.get("rsp_cd") or payload.get("response_code") or "00000").strip()
    if operation in _ORDER_SUCCESS_CODES:
        return code in _ORDER_SUCCESS_CODES[operation]
    return code in ("00000", "0")


def _error_payload(config: KoreanConnectorConfig, payload: Mapping[str, Any], *, symbol: str | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "environment": config.environment,
        "symbol": symbol,
        "error": str(payload.get("rsp_msg") or payload.get("msg") or payload.get("error_description") or payload.get("error") or "LS API error"),
        "code": payload.get("rsp_cd") or payload.get("response_code"),
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
    if len(token) == 7 and token.startswith("A") and token[1:].isdigit():
        token = token[1:]
    return token


def _order_symbol(symbol: str) -> str:
    token = _normalize_kr_symbol(symbol)
    if len(token) == 6 and token.isdigit():
        return f"A{token}"
    return token


def _order_condition_code(time_in_force: str) -> str:
    token = str(time_in_force or "day").strip().lower()
    if token == "ioc":
        return "1"
    if token == "fok":
        return "2"
    return "0"


def _position_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(item.get("expcode") or "").strip(),
        "name": str(item.get("hname") or "").strip(),
        "quantity": _to_float(item.get("janqty")),
        "market_value": _to_float(item.get("mamt")),
        "last_price": _to_float(item.get("price")),
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


def _websocket_kind(tr_cd: str) -> str:
    token = str(tr_cd or "").strip()
    for spec in LS_WEBSOCKET_CHANNELS.values():
        if spec["tr_cd"] == token:
            return spec["kind"]
    if token in {"S3_", "K3_", "NS3", "US3", "DS3", "DK3"}:
        return "trade"
    if token in {"H1_", "HA_", "NH1", "UH1", "DH1", "DHA", "B7_"}:
        return "orderbook"
    if token.startswith("SC"):
        return {
            "SC0": "order_accept",
            "SC1": "order_execution",
            "SC2": "order_modify",
            "SC3": "order_cancel",
            "SC4": "order_reject",
        }.get(token, "order_event")
    return ""


def _price_levels(body: Mapping[str, Any], *, price_prefix: str, qty_prefix: str) -> list[dict[str, float | None]]:
    levels: list[dict[str, float | None]] = []
    for idx in range(1, 11):
        price = _to_float(body.get(f"{price_prefix}{idx}"))
        quantity = _to_float(body.get(f"{qty_prefix}{idx}"))
        if price is None and quantity is None:
            continue
        levels.append({"price": price, "quantity": quantity})
    return levels


def _order_side_from_code(value: Any) -> str:
    code = str(value or "").strip()
    if code == "2":
        return "buy"
    if code == "1":
        return "sell"
    return code


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _numeric_value(value: float | int | str) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric
