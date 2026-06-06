"""Toss Securities Open API REST connector.

Toss publishes a canonical OpenAPI 3.1 document at
``https://openapi.tossinvest.com/openapi-docs/latest/openapi.json``. This
module fixes the Vibe-Trading adapter to that public REST shape while keeping
credentialed smoke checks as a separate approval-gated step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.config.paths import get_runtime_root
from src.trading.connectors.kr_common import (
    KoreanConnectorConfig,
    build_config as _build_config,
    check_status as _check_status,
    load_config as _load_config,
    save_config as _save_config,
)

CONFIG_FILENAME = "toss.json"
BASE_URL = "https://openapi.tossinvest.com"
LABEL = "Toss Securities Open API"
CONNECTOR = "toss"


def config_path() -> Path:
    return get_runtime_root() / CONFIG_FILENAME


def load_config() -> KoreanConnectorConfig:
    return _load_config(config_path(), connector=CONNECTOR, paper_url=BASE_URL, live_url=BASE_URL)


def save_config(config: KoreanConnectorConfig) -> Path:
    return _save_config(config_path(), config)


def build_config(profile_config: Mapping[str, Any] | None = None, overrides: Mapping[str, Any] | None = None) -> KoreanConnectorConfig:
    return _build_config(
        config_path=config_path(),
        connector=CONNECTOR,
        profile_config=profile_config,
        overrides=overrides,
        paper_url=BASE_URL,
        live_url=BASE_URL,
    )


def check_status(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    report = _check_status(config or load_config(), label=LABEL)
    report["openapi"] = {
        "server": BASE_URL,
        "source": "https://openapi.tossinvest.com/openapi-docs/latest/openapi.json",
    }
    return report


def get_account_snapshot(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(cfg, "/api/v1/accounts", token=token)
    accounts = payload.get("result") or []
    return {"status": "ok", "profile": cfg.profile, "accounts": accounts}


def get_positions(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(cfg, "/api/v1/holdings", token=token, account_required=True)
    result = payload.get("result") or {}
    return {
        "status": "ok",
        "profile": cfg.profile,
        "summary": {key: value for key, value in result.items() if key != "items"},
        "positions": list(result.get("items") or []),
    }


def get_open_orders(config: KoreanConnectorConfig | None = None, *, include_executions: bool = False) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(
        cfg,
        "/api/v1/orders",
        token=token,
        account_required=True,
        params={"status": "OPEN"},
    )
    result = payload.get("result") or {}
    orders = list(result.get("orders") or [])
    response: dict[str, Any] = {"status": "ok", "profile": cfg.profile, "open_orders": orders}
    if include_executions:
        response["executions"] = [order for order in orders if (order.get("execution") or {}).get("filledQuantity")]
    return response


def get_order(config: KoreanConnectorConfig | None = None, order_id: str = "") -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(cfg, f"/api/v1/orders/{_path_part(order_id)}", token=token, account_required=True)
    return {"status": "ok", "profile": cfg.profile, "order": payload.get("result") or payload}


def get_buying_power(config: KoreanConnectorConfig | None = None, *, currency: str = "KRW") -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(
        cfg,
        "/api/v1/buying-power",
        token=token,
        account_required=True,
        params={"currency": str(currency or "").strip().upper()},
    )
    result = payload.get("result") or {}
    return {
        "status": "ok",
        "profile": cfg.profile,
        "buying_power": result,
        "currency": result.get("currency"),
        "cash_buying_power": result.get("cashBuyingPower"),
    }


def get_sellable_quantity(config: KoreanConnectorConfig | None = None, *, symbol: str) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    cleaned_symbol = _clean_symbol(symbol)
    payload = _api_get(
        cfg,
        "/api/v1/sellable-quantity",
        token=token,
        account_required=True,
        params={"symbol": cleaned_symbol},
    )
    result = payload.get("result") or {}
    return {
        "status": "ok",
        "profile": cfg.profile,
        "symbol": cleaned_symbol,
        "sellable_quantity": result.get("sellableQuantity"),
        "result": result,
    }


def get_commissions(config: KoreanConnectorConfig | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(cfg, "/api/v1/commissions", token=token, account_required=True)
    return {"status": "ok", "profile": cfg.profile, "commissions": list(payload.get("result") or [])}


def get_quote(symbol: str, *, config: KoreanConnectorConfig | None = None, **_: Any) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_get(cfg, "/api/v1/prices", token=token, params={"symbols": _clean_symbol(symbol)})
    rows = list(payload.get("result") or [])
    return {"status": "ok", "profile": cfg.profile, "quote": rows[0] if rows else {}, "quotes": rows}


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig | None = None,
    period: str = "1d",
    limit: int = 90,
    adjusted: bool = True,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    interval = "1m" if str(period).lower() == "1m" else "1d"
    count = max(1, min(int(limit), 200))
    payload = _api_get(
        cfg,
        "/api/v1/candles",
        token=token,
        params={"symbol": _clean_symbol(symbol), "interval": interval, "count": count, "adjusted": adjusted},
    )
    result = payload.get("result") or {}
    bars = [
        {
            "timestamp": item.get("timestamp"),
            "open": item.get("openPrice"),
            "high": item.get("highPrice"),
            "low": item.get("lowPrice"),
            "close": item.get("closePrice"),
            "volume": item.get("volume"),
            "currency": item.get("currency"),
            "raw": item,
        }
        for item in list(result.get("candles") or [])
    ]
    return {"status": "ok", "profile": cfg.profile, "bars": bars, "next_before": result.get("nextBefore")}


def place_order(config: KoreanConnectorConfig | None = None, **kwargs: Any) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    body = _order_body(kwargs)
    payload = _api_post(cfg, "/api/v1/orders", token=token, account_required=True, json_body=body)
    return {"status": "ok", "profile": cfg.profile, "order": payload.get("result") or payload}


def modify_order(
    config: KoreanConnectorConfig | None = None,
    order_id: str = "",
    *,
    order_type: str = "limit",
    quantity: float | int | str | None = None,
    limit_price: float | int | str | None = None,
    confirm_high_value_order: bool | None = None,
    **_: Any,
) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    body: dict[str, Any] = {"orderType": _order_type(order_type)}
    if quantity is not None:
        body["quantity"] = _decimal_string(quantity)
    if limit_price is not None:
        body["price"] = _decimal_string(limit_price)
    if confirm_high_value_order is not None:
        body["confirmHighValueOrder"] = bool(confirm_high_value_order)
    payload = _api_post(cfg, f"/api/v1/orders/{_path_part(order_id)}/modify", token=token, account_required=True, json_body=body)
    return {"status": "ok", "profile": cfg.profile, "order": payload.get("result") or payload}


def cancel_order(config: KoreanConnectorConfig | None = None, order_id: str = "", **_: Any) -> dict[str, Any]:
    cfg = config or load_config()
    token = _access_token(cfg)
    payload = _api_post(cfg, f"/api/v1/orders/{_path_part(order_id)}/cancel", token=token, account_required=True, json_body={})
    return {"status": "ok", "profile": cfg.profile, "order": payload.get("result") or payload}


def _access_token(config: KoreanConnectorConfig) -> str:
    _require_credentials(config)
    payload = _request_json(
        "POST",
        _url(config, "/oauth2/token"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        form={
            "grant_type": "client_credentials",
            "client_id": config.app_key,
            "client_secret": config.app_secret,
        },
        timeout=config.timeout,
    )
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Toss Securities Open API token response did not include access_token")
    return token


def _api_get(
    config: KoreanConnectorConfig,
    path: str,
    *,
    token: str,
    params: Mapping[str, Any] | None = None,
    account_required: bool = False,
) -> dict[str, Any]:
    return _request_json("GET", _url(config, path), headers=_headers(config, token, account_required=account_required), params=dict(params or {}), timeout=config.timeout)


def _api_post(
    config: KoreanConnectorConfig,
    path: str,
    *,
    token: str,
    json_body: Mapping[str, Any],
    account_required: bool,
) -> dict[str, Any]:
    return _request_json("POST", _url(config, path), headers=_headers(config, token, account_required=account_required), json_body=dict(json_body), timeout=config.timeout)


def _headers(config: KoreanConnectorConfig, token: str, *, account_required: bool) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if account_required:
        if not config.account:
            raise RuntimeError(f"{LABEL} connector not configured: missing account.")
        headers["X-Tossinvest-Account"] = config.account
    return headers


def _order_body(values: Mapping[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": _clean_symbol(values.get("symbol")),
        "side": str(values.get("side") or "").strip().upper(),
        "orderType": _order_type(values.get("order_type") or values.get("orderType") or "market"),
    }
    if values.get("client_order_id"):
        body["clientOrderId"] = str(values["client_order_id"]).strip()
    if values.get("time_in_force"):
        tif = str(values["time_in_force"]).strip().upper()
        if tif and tif != "DAY":
            body["timeInForce"] = tif
    if values.get("notional") is not None:
        body["orderAmount"] = _decimal_string(values["notional"])
    elif values.get("order_amount") is not None:
        body["orderAmount"] = _decimal_string(values["order_amount"])
    elif values.get("quantity") is not None:
        body["quantity"] = _decimal_string(values["quantity"])
    if values.get("limit_price") is not None:
        body["price"] = _decimal_string(values["limit_price"])
    if values.get("confirm_high_value_order") is not None:
        body["confirmHighValueOrder"] = bool(values["confirm_high_value_order"])
    return body


def _request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    json_body: Mapping[str, Any] | None = None,
    form: Mapping[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    target = url
    if params:
        clean_params = {key: value for key, value in params.items() if value is not None}
        target = f"{target}?{urlencode(clean_params)}"
    payload: bytes | None = None
    request_headers = dict(headers or {})
    if json_body is not None:
        payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        payload = urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = Request(target, data=payload, headers=request_headers, method=method.upper())
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - connector URL is user/profile controlled.
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _url(config: KoreanConnectorConfig, path: str) -> str:
    return f"{config.endpoint.rstrip('/')}/{path.lstrip('/')}"


def _require_credentials(config: KoreanConnectorConfig) -> None:
    missing = [name for name in ("app_key", "app_secret") if not getattr(config, name)]
    if missing:
        raise RuntimeError(f"{LABEL} connector not configured: missing {', '.join(missing)}.")


def _clean_symbol(symbol: Any) -> str:
    value = str(symbol or "").strip().upper()
    if not value:
        raise ValueError("symbol must not be blank")
    return value


def _path_part(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("order_id must not be blank")
    return cleaned


def _order_type(value: Any) -> str:
    normalized = str(value or "market").strip().upper()
    if normalized in {"MKT", "MARKET"}:
        return "MARKET"
    if normalized in {"LMT", "LIMIT"}:
        return "LIMIT"
    return normalized


def _decimal_string(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
