"""KIS Open API connector.

The endpoint catalog and TR IDs are derived from Korea Investment & Securities'
official ``open-trading-api`` samples. This module does not vendor that code;
it implements Vibe-Trading's own small REST adapter around the official
contract.
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
)

CONFIG_FILENAME = "kis.json"
PAPER_URL = "https://openapivts.koreainvestment.com:29443"
LIVE_URL = "https://openapi.koreainvestment.com:9443"
LABEL = "KIS Open API"
CONNECTOR = "kis"

KIS_DOMESTIC_STOCK_ENDPOINTS: dict[str, dict[str, str]] = {
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
    report["official_catalog"] = "domestic_stock"
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


def get_open_orders(config: KoreanConnectorConfig | None = None, *, include_executions: bool = False) -> dict[str, Any]:
    cfg = config or load_config()
    return {
        "status": "error",
        "profile": cfg.profile,
        "error": "KIS open-order read is not implemented yet; add inquire-psbl-rvsecncl/order ledger contract first.",
    }


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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
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
