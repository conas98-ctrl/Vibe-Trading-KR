"""DB Securities Open API connector.

The endpoint catalog is derived from DB Securities' official Open API portal
JSON surface verified for this Korean-market port: token issuance, domestic
PRICE current quote, CSPAQ03420 balance, CSPAQ04800 execution/open order
inquiry, CSPAT00600/CSPAT00700/CSPAT00800 stock order flows, overseas
FSTKPRICE current quote, and CAZCT00100 overseas stock order. WebSocket
channels are derived from the same official portal JSON for domestic stock
real-time quote, order book, and order events.
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
    cached_access_token as _cached_access_token,
    check_status as _check_status,
    load_config as _load_config,
    save_config as _save_config,
)

CONFIG_FILENAME = "db.json"
PAPER_URL = "https://openapi.dbsec.co.kr:8443"
LIVE_URL = "https://openapi.dbsec.co.kr:8443"
LABEL = "DB Securities Open API"
CONNECTOR = "db"

DB_OPENAPI_ENDPOINTS: dict[str, dict[str, str]] = {
    "auth_token": {
        "method": "POST",
        "path": "/oauth2/token",
        "content_type": "application/x-www-form-urlencoded",
    },
    "stock_quote": {
        "method": "POST",
        "path": "/api/v1/quote/kr-stock/inquiry/price",
        "tr_code": "PRICE",
    },
    "overseas_stock_quote": {
        "method": "POST",
        "path": "/api/v1/quote/overseas-stock/inquiry/price",
        "tr_code": "FSTKPRICE",
    },
    "account_balance": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/inquiry/balance",
        "tr_code": "CSPAQ03420",
    },
    "open_orders": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/inquiry/transaction-history",
        "tr_code": "CSPAQ04800",
    },
    "stock_order": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order",
        "tr_code": "CSPAT00600",
    },
    "modify_order": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order-revision",
        "tr_code": "CSPAT00700",
    },
    "cancel_order": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order-cancel",
        "tr_code": "CSPAT00800",
    },
    "stock_order_nxt": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order-nxt",
        "tr_code": "CSPAT00610",
    },
    "overseas_stock_order": {
        "method": "POST",
        "path": "/api/v1/trading/overseas-stock/order",
        "tr_code": "CAZCT00100",
    },
    "modify_order_nxt": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order-revision-nxt",
        "tr_code": "CSPAT00710",
    },
    "cancel_order_nxt": {
        "method": "POST",
        "path": "/api/v1/trading/kr-stock/order-cancel-nxt",
        "tr_code": "CSPAT00810",
    },
    "websocket_disconnect_session": {
        "method": "POST",
        "path": "/api/v1/websocket/disconnectSession",
        "tr_code": "DisconnectSession",
    },
}

DB_WEBSOCKET_URLS: dict[str, str] = {
    "paper": "wss://openapi.dbsec.co.kr:17070",
    "live": "wss://openapi.dbsec.co.kr:7070",
}

DB_WEBSOCKET_CHANNELS: dict[str, dict[str, str]] = {
    "trade": {
        "path": "/pub/S00",
        "tr_code": "S00",
        "tr_type": "1",
    },
    "orderbook": {
        "path": "/pub/S01",
        "tr_code": "S01",
        "tr_type": "1",
    },
    "order_accept": {
        "path": "/pub/IS0",
        "tr_code": "IS0",
        "tr_type": "3",
    },
    "order_execution": {
        "path": "/pub/IS1",
        "tr_code": "IS1",
        "tr_type": "3",
    },
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
    report["auth_probe_reason"] = "DB token issuance is deferred until an explicit read/order call."
    report["official_catalog"] = (
        "PRICE,CSPAQ03420,CSPAQ04800,CSPAT00600,CSPAT00700,CSPAT00800,"
        "CSPAT00610,CSPAT00710,CSPAT00810,FSTKPRICE,CAZCT00100,"
        "S00,S01,IS0,IS1,DisconnectSession"
    )
    return report


def get_account_snapshot(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    payload = _request_json(cfg, "account_balance", body={"In": {"QryTpCode0": "0"}}, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)
    raw_account = _first_mapping(payload.get("Out"))
    positions = [_position_to_dict(item) for item in _as_list(payload.get("Out1"))]
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "account": {
            "cash": _to_float(raw_account.get("DpsastAmt")),
            "total_value": _to_float(raw_account.get("TotEvalAmt")),
            "unrealized_pnl": _to_float(raw_account.get("TotEvalPnlAmt")),
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
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    body = {
        "In": {
            "ExecYn": "0",
            "BnsTpCode": "0",
            "IsuTpCode": "0",
            "QryTp": "0",
            "TrdMktCode": "0",
            "SorTpYn": "2",
        }
    }
    payload = _request_json(cfg, "open_orders", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload)
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "orders": [_open_order_to_dict(item) for item in _as_list(payload.get("Out1"))],
        "raw": payload,
    }


def get_quote(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    client: Any | None = None,
    market_code: str = "J",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_kr_symbol(symbol)
    body = {"In": {"InputIscd1": clean, "InputCondMrktDivCode": market_code}}
    payload = _request_json(cfg, "stock_quote", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    raw = _first_mapping(payload.get("Out"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "quote": {
            "last": _to_float(raw.get("Prpr")),
            "change": _to_float(raw.get("PrdyVrss")),
            "change_rate": _to_float(raw.get("PrdyCtrt")),
            "volume": _to_float(raw.get("AcmlVol")),
            "open": _to_float(raw.get("Oprc")),
            "high": _to_float(raw.get("Hprc")),
            "low": _to_float(raw.get("Lprc")),
            "raw": raw,
        },
    }


def get_overseas_quote(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    client: Any | None = None,
    market_code: str = "FN",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)

    clean = _normalize_overseas_symbol(symbol)
    if not clean:
        return {"status": "error", "profile": cfg.profile, "error": "DB overseas quote requires a symbol."}
    body = {"In": {"InputIscd1": clean, "InputCondMrktDivCode": str(market_code or "FN").strip().upper()}}
    payload = _request_json(cfg, "overseas_stock_quote", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    raw = _first_mapping(payload.get("Out"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "symbol": clean,
        "market_code": body["In"]["InputCondMrktDivCode"],
        "quote": {
            "last": _to_float(raw.get("Prpr")),
            "previous_close": _to_float(raw.get("Sdpr")),
            "change": _to_float(raw.get("PrdyVrss")),
            "change_rate": _to_float(raw.get("PrdyCtrt")),
            "volume": _to_float(raw.get("AcmlVol")),
            "previous_volume": _to_float(raw.get("prdyVol")),
            "open": _to_float(raw.get("Oprc")),
            "high": _to_float(raw.get("Hprc")),
            "low": _to_float(raw.get("Lprc")),
            "per": _to_float(raw.get("Per")),
            "bid1": _to_float(raw.get("bidp1")),
            "ask1": _to_float(raw.get("askp1")),
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
        "error": "DB historical bars are not implemented yet; only the official PRICE quote contract is pinned in this slice.",
    }


def websocket_url(config: KoreanConnectorConfig | None = None) -> str:
    """Return DB's official WebSocket endpoint for the active profile."""
    cfg = config or load_config()
    return DB_WEBSOCKET_URLS["paper"] if cfg.environment == "paper" else DB_WEBSOCKET_URLS["live"]


def build_websocket_subscribe_message(
    symbol: str,
    *,
    channel: str,
    config: KoreanConnectorConfig | None = None,
    client: Any | None = None,
    market_code: str = "J",
) -> dict[str, Any]:
    """Build a DB WebSocket subscription frame from the official examples."""
    cfg = config or load_config()
    spec = DB_WEBSOCKET_CHANNELS.get(str(channel or "").strip().lower())
    if spec is None:
        raise KoreanConnectorConfigError(f"unsupported DB WebSocket channel: {channel!r}")
    token = cfg.access_token
    if not token:
        if client is None:
            raise KoreanConnectorConfigError("DB WebSocket subscriptions require access_token or a client for token issuance.")
        token = _access_token(cfg, client)

    body: dict[str, Any] = {"tr_cd": spec["tr_code"]}
    if spec["tr_code"] in {"S00", "S01"}:
        clean = _normalize_kr_symbol(symbol)
        if not clean:
            raise KoreanConnectorConfigError(f"DB WebSocket channel {channel!r} requires a symbol.")
        body["tr_key"] = f"{str(market_code or 'J').strip().upper()} {clean}"
    return {"header": {"token": token, "tr_type": spec["tr_type"]}, "body": body}


def disconnect_websocket_sessions(config: KoreanConnectorConfig | None = None, *, client: Any | None = None) -> dict[str, Any]:
    """Call DB's official WebSocket session reset endpoint."""
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    payload = _request_json(cfg, "websocket_disconnect_session", body={}, client=client)
    if payload.get("error") or payload.get("rsp_cd") not in (None, "00000", "0"):
        return _error_payload(cfg, payload)
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "account": str(payload.get("acntNo") or ""),
        "result": str(payload.get("result") or ""),
        "raw": payload,
    }


def parse_websocket_message(message: Mapping[str, Any] | str) -> dict[str, Any]:
    """Normalize DB WebSocket event payloads into stable event dictionaries."""
    payload = json.loads(message) if isinstance(message, str) else dict(message)
    header = _first_mapping(payload.get("header"))
    body = _first_mapping(payload.get("body"))
    tr_code = str(header.get("tr_cd") or body.get("tr_cd") or "").strip().upper()

    if tr_code == "S00":
        symbol = _normalize_kr_symbol(str(body.get("ShrnIscd") or ""))
        return {
            "status": "ok",
            "channel": "trade",
            "symbol": symbol,
            "quote": {
                "last": _to_float(body.get("StckPrpr")),
                "change": _to_float(body.get("PrdyVrss")),
                "change_rate": _to_float(body.get("PrdyCtrt")),
                "open": _to_float(body.get("StckOprc")),
                "high": _to_float(body.get("StckHgpr")),
                "low": _to_float(body.get("StckLwpr")),
                "trade_volume": _to_float(body.get("CntgVol")),
                "volume": _to_float(body.get("AcmlVol")),
                "ask1": _to_float(body.get("Askp1")),
                "bid1": _to_float(body.get("Bidp1")),
                "raw": body,
            },
            "raw": payload,
        }

    if tr_code == "S01":
        symbol = _normalize_kr_symbol(str(body.get("ShrnIscd") or ""))
        asks = _price_levels(body, price_prefix="Askp", qty_prefix="AskpRsqn")
        bids = _price_levels(body, price_prefix="Bidp", qty_prefix="BidpRsqn")
        return {
            "status": "ok",
            "channel": "orderbook",
            "symbol": symbol,
            "orderbook": {
                "asks": asks,
                "bids": bids,
                "total_ask_quantity": _to_float(body.get("TotalAskprsqn")),
                "total_bid_quantity": _to_float(body.get("TotalBidprsqn")),
                "raw": body,
            },
            "raw": payload,
        }

    if tr_code in {"IS0", "IS1"}:
        return {
            "status": "ok",
            "channel": "order_accept" if tr_code == "IS0" else "order_execution",
            "order": {
                "account": str(body.get("Sacntno") or "").strip(),
                "symbol": _normalize_kr_symbol(str(body.get("Sshtnisuno") or body.get("Sisuno") or "")),
                "order_id": str(body.get("Sordno") or "").strip(),
                "original_order_id": str(body.get("Sorgordno") or "").strip(),
                "execution_id": str(body.get("Sexecno") or "").strip(),
                "order_quantity": _to_float(body.get("Sordqty")),
                "order_price": _to_float(body.get("Sordprc")),
                "executed_quantity": _to_float(body.get("Sexecqty")),
                "executed_price": _to_float(body.get("Sexecprc")),
                "raw": body,
            },
            "raw": payload,
        }

    return {"status": "ok", "channel": tr_code.lower() or "unknown", "raw": payload}


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
        return {"status": "error", "profile": cfg.profile, "error": "DB orders require quantity; notional-only orders are unsupported."}
    if notional is not None and quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "DB orders require explicit quantity."}

    clean_side = str(side or "").strip().lower()
    if clean_side not in ("buy", "sell"):
        return {"status": "error", "profile": cfg.profile, "error": "DB order side must be 'buy' or 'sell'."}
    bns_tp_code = "2" if clean_side == "buy" else "1"
    domestic_symbol = _normalize_kr_symbol(symbol)
    if _looks_like_overseas_symbol(symbol) or not (len(domestic_symbol) == 6 and domestic_symbol.isdigit()):
        return {
            "status": "error",
            "profile": cfg.profile,
            "error": "DB domestic place_order requires a 6-digit Korean symbol; use place_overseas_stock_order for overseas stocks.",
        }

    clean_type = str(order_type or "market").strip().lower()
    if clean_type == "limit":
        if limit_price is None:
            return {"status": "error", "profile": cfg.profile, "error": "DB limit orders require limit_price."}
        ordprc_ptn_code = "00"
        ord_prc = _numeric_value(limit_price)
    elif clean_type == "market":
        ordprc_ptn_code = "03"
        ord_prc = 0
    else:
        return {"status": "error", "profile": cfg.profile, "error": "DB order_type must be 'market' or 'limit'."}

    is_nxt = _is_nxt_exchange(exchange)
    order_input: dict[str, Any] = {
        "IsuNo": domestic_symbol,
        "OrdQty": _numeric_value(quantity),
        "OrdPrc": ord_prc,
        "BnsTpCode": bns_tp_code,
        "OrdprcPtnCode": ordprc_ptn_code,
        "MgntrnCode": "000",
        "LoanDt": "00000000",
        "OrdCndiTpCode": _order_condition_code(time_in_force),
    }
    if not is_nxt:
        order_input["TrchNo"] = _exchange_trch_no(exchange)
    body = {"In": order_input}
    payload = _request_json(cfg, "stock_order_nxt" if is_nxt else "stock_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["In"]["IsuNo"])
    output = _first_mapping(payload.get("Out"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "paper_guard": "profile_endpoint_separated",
        "symbol": body["In"]["IsuNo"],
        "side": clean_side,
        "quantity": _to_float(body["In"]["OrdQty"]),
        "order_type": clean_type,
        "order_id": str(output.get("OrdNo") or ""),
        "broker_order_ref": output,
        "raw": payload,
    }


def place_overseas_stock_order(
    config: KoreanConnectorConfig | None = None,
    *,
    symbol: str,
    side: str,
    quantity: float | int | str | None = None,
    order_type: str = "market",
    client: Any | None = None,
    order_trade_type_code: str = "0",
    original_order_id: int | str = 0,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "DB overseas stock orders require quantity."}

    clean_side = str(side or "").strip().lower()
    if clean_side not in ("buy", "sell"):
        return {"status": "error", "profile": cfg.profile, "error": "DB overseas order side must be 'buy' or 'sell'."}
    clean_type = str(order_type or "market").strip().lower()
    if clean_type != "market":
        return {
            "status": "error",
            "profile": cfg.profile,
            "error": "DB overseas stock order contract currently pins only the official market-order example.",
        }

    clean = _normalize_overseas_symbol(symbol)
    if not clean:
        return {"status": "error", "profile": cfg.profile, "error": "DB overseas stock order requires a symbol."}
    body = {
        "In": {
            "AstkIsuNo": clean,
            "AstkBnsTpCode": "2" if clean_side == "buy" else "1",
            "AstkOrdprcPtnCode": "2",
            "AstkOrdCndiTpCode": "1",
            "AstkOrdQty": _numeric_value(quantity),
            "AstkOrdPrc": 0,
            "OrdTrdTpCode": str(order_trade_type_code or "0").strip(),
            "OrgOrdNo": _numeric_value(original_order_id),
        }
    }
    payload = _request_json(cfg, "overseas_stock_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=clean)
    output = _first_mapping(payload.get("Out"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "paper_guard": "profile_endpoint_separated",
        "symbol": clean,
        "side": clean_side,
        "quantity": _to_float(body["In"]["AstkOrdQty"]),
        "order_type": clean_type,
        "order_id": str(output.get("OrdNo") or ""),
        "broker_order_ref": output,
        "raw": payload,
    }


def modify_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    symbol: str | None = None,
    quantity: float | int | str | None = None,
    limit_price: float | int | str | None = None,
    time_in_force: str = "day",
    client: Any | None = None,
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "DB modify_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "DB modify_order requires symbol."}
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "DB modify_order requires quantity."}
    if limit_price is None:
        return {"status": "error", "profile": cfg.profile, "error": "DB modify_order requires limit_price."}

    body = {
        "In": {
            "OrgOrdNo": _numeric_value(order_id),
            "IsuNo": _prefixed_kr_symbol(symbol),
            "OrdQty": _numeric_value(quantity),
            "OrdprcPtnCode": "00",
            "OrdCndiTpCode": _order_condition_code(time_in_force),
            "OrdPrc": _numeric_value(limit_price),
        }
    }
    payload = _request_json(cfg, "modify_order_nxt" if _is_nxt_exchange(exchange) else "modify_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["In"]["IsuNo"])
    output = _first_mapping(payload.get("Out"))
    return {
        "status": "ok",
        "profile": cfg.profile,
        "environment": cfg.environment,
        "order_id": str(order_id),
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
    exchange: str = "KRX",
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    missing = _missing_auth_fields(cfg)
    if missing:
        return _not_configured(cfg, missing)
    if not str(order_id or "").strip():
        return {"status": "error", "profile": cfg.profile, "error": "DB cancel_order requires order_id."}
    if not symbol:
        return {"status": "error", "profile": cfg.profile, "error": "DB cancel_order requires symbol."}
    if quantity is None:
        return {"status": "error", "profile": cfg.profile, "error": "DB cancel_order requires quantity because CSPAT00800 requires OrdQty."}

    body = {"In": {"OrgOrdNo": _numeric_value(order_id), "IsuNo": _prefixed_kr_symbol(symbol), "OrdQty": _numeric_value(quantity)}}
    payload = _request_json(cfg, "cancel_order_nxt" if _is_nxt_exchange(exchange) else "cancel_order", body=body, client=client)
    if not _payload_ok(payload):
        return _error_payload(cfg, payload, symbol=body["In"]["IsuNo"])
    return {"status": "ok", "profile": cfg.profile, "environment": cfg.environment, "order_id": str(order_id), "raw": payload}


def _request_json(
    config: KoreanConnectorConfig,
    operation: str,
    *,
    body: Mapping[str, Any],
    client: Any | None = None,
) -> dict[str, Any]:
    with _client(config, client) as active:
        token = _access_token(config, active)
        endpoint = DB_OPENAPI_ENDPOINTS[operation]
        url = config.endpoint.rstrip("/") + endpoint["path"]
        response = active.post(
            url,
            json=dict(body),
            headers=_headers(token),
            timeout=config.timeout,
        )
        return _response_json(response)


def _access_token(config: KoreanConnectorConfig, client: Any) -> str:
    if config.access_token:
        return config.access_token
    missing = _missing_auth_fields(config)
    if missing:
        raise KoreanConnectorConfigError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")
    return _cached_access_token(config, lambda: _issue_access_token(config, client))


def _issue_access_token(config: KoreanConnectorConfig, client: Any) -> tuple[str, float | None]:
    url = config.endpoint.rstrip("/") + DB_OPENAPI_ENDPOINTS["auth_token"]["path"]
    response = client.post(
        url,
        params={"appkey": config.app_key, "appsecretkey": config.app_secret, "grant_type": "client_credentials", "scope": "oob"},
        headers={"content-type": DB_OPENAPI_ENDPOINTS["auth_token"]["content_type"]},
        timeout=config.timeout,
    )
    payload = _response_json(response)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise KoreanConnectorConfigError(f"{LABEL} auth token response missing access_token.")
    expires_in = payload.get("expires_in")
    return token, float(expires_in) if expires_in else None


def _headers(token: str) -> dict[str, str]:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "cont_yn": "N",
        "cont_key": "",
    }


@contextmanager
def _client(config: KoreanConnectorConfig, client: Any | None = None) -> Iterator[Any]:
    if client is not None:
        yield client
        return
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise KoreanConnectorConfigError("DB REST calls require httpx; install project dependencies first.") from exc
    with httpx.Client(timeout=config.timeout, follow_redirects=True, trust_env=True) as active:
        yield active


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    payload = response.json()
    return dict(payload or {}) if isinstance(payload, Mapping) else {"raw": payload}


def _payload_ok(payload: Mapping[str, Any]) -> bool:
    code = str(payload.get("rsp_cd") or payload.get("response_code") or "00000").strip()
    return code in ("00000", "0")


def _error_payload(config: KoreanConnectorConfig, payload: Mapping[str, Any], *, symbol: str | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "environment": config.environment,
        "symbol": symbol,
        "error": str(payload.get("rsp_msg") or payload.get("msg") or payload.get("error_description") or payload.get("error") or "DB API error"),
        "code": payload.get("rsp_cd") or payload.get("response_code"),
        "raw": dict(payload),
    }


def _not_configured(config: KoreanConnectorConfig, missing: list[str]) -> dict[str, Any]:
    return {
        "status": "error",
        "connector": CONNECTOR,
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
    if token.startswith("U-"):
        token = token[2:]
    if token.startswith("A") and len(token) == 7 and token[1:].isdigit():
        token = token[1:]
    for suffix in (".KS", ".KQ"):
        if token.endswith(suffix):
            token = token[: -len(suffix)]
    return token


def _normalize_overseas_symbol(symbol: str) -> str:
    token = str(symbol or "").strip().upper()
    if token.startswith(("US.", "USA.")):
        token = token.split(".", 1)[1]
    if token.endswith((".US", ".USA")):
        token = token.rsplit(".", 1)[0]
    if token.startswith(("NASDAQ:", "NYSE:", "AMEX:")):
        token = token.split(":", 1)[1]
    return token


def _looks_like_overseas_symbol(symbol: str) -> bool:
    token = str(symbol or "").strip().upper()
    return (
        token.startswith(("US.", "USA.", "NASDAQ:", "NYSE:", "AMEX:"))
        or token.endswith((".US", ".USA"))
    )


def _prefixed_kr_symbol(symbol: str) -> str:
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


def _exchange_trch_no(exchange: str) -> int:
    token = str(exchange or "KRX").strip().upper()
    if token and token != "KRX":
        return 1
    return 1


def _is_nxt_exchange(exchange: str) -> bool:
    return str(exchange or "").strip().upper() in {"NXT", "NEXTRADE", "NEXT"}


def _position_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": _normalize_kr_symbol(str(item.get("IsuNo") or "")),
        "name": str(item.get("IsuNm") or "").strip(),
        "quantity": _to_float(_first_value(item, "BalQty0", "BalQty", "FlctQty")),
        "available_quantity": _to_float(item.get("AbleQty")),
        "market_value": _to_float(item.get("EvalAmt")),
        "cost_basis": _to_float(item.get("PchsAmt")),
        "last_price": _to_float(item.get("NowPrc")),
        "raw": dict(item),
    }


def _open_order_to_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "order_id": str(item.get("OrdNo") or "").strip(),
        "original_order_id": str(item.get("OrgOrdNo") or "").strip(),
        "symbol": _normalize_kr_symbol(str(item.get("IsuNo") or "")),
        "side": _side_name(item.get("BnsTpCode")),
        "quantity": _to_float(item.get("OrdQty")),
        "executed_quantity": _to_float(item.get("AllExecQty")),
        "remaining_quantity": _to_float(item.get("MrcAbleQty")),
        "limit_price": _to_float(item.get("OrdPrc")),
        "transaction_time": str(item.get("TrxTime") or "").strip(),
        "raw": dict(item),
    }


def _side_name(value: Any) -> str:
    code = str(value or "").strip()
    if code == "2":
        return "buy"
    if code == "1":
        return "sell"
    return code


def _price_levels(body: Mapping[str, Any], *, price_prefix: str, qty_prefix: str) -> list[dict[str, float | None]]:
    levels: list[dict[str, float | None]] = []
    for index in range(1, 11):
        price = _to_float(body.get(f"{price_prefix}{index}"))
        quantity = _to_float(body.get(f"{qty_prefix}{index}"))
        if price is None and quantity is None:
            continue
        levels.append({"price": price, "quantity": quantity})
    return levels


def _first_value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _numeric_value(value: float | int | str) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric
