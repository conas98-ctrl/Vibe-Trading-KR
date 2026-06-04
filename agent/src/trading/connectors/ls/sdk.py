"""LS Securities OpenAPI connector.

The REST catalog here is limited to LS Securities' official OpenAPI sample and
guide JSON surface verified for this port: token issuance, t1101 stock quote,
t0424 account balance, and CSPAT00601/CSPAT00701/CSPAT00801 stock order flows.
"""

from __future__ import annotations

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
    report["official_catalog"] = "token,t1101,t0424,CSPAT00601,CSPAT00701,CSPAT00801"
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
