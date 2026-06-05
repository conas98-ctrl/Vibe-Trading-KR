"""Kiwoom REST OpenAPI connector.

The endpoint catalog is derived from Kiwoom's official OpenAPI guide pages.
Only verified REST contracts are exposed; anything outside this catalog stays
fail-closed until its official request/response surface is pinned by tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
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
    report["official_catalog"] = "ka10001,ka10081,kt00018,ka10075,kt10000,kt10001,kt10002,kt10003"
    return report


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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _numeric_string(value: float | int | str) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else str(numeric)
