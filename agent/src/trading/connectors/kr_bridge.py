"""Shared read-only HTTP client for Korean Windows broker local bridges."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping
from urllib.parse import quote

from src.trading.connectors.kr_common import KoreanConnectorConfig, KoreanConnectorConfigError, public_config


def check_bridge_status(config: KoreanConnectorConfig, *, label: str, client: Any | None = None) -> dict[str, Any]:
    missing = _missing_bridge_fields(config)
    report: dict[str, Any] = {
        "status": "ok" if not missing else "error",
        "connector": config.connector,
        "transport": "local_bridge",
        "config": public_config(config),
        "endpoint": config.bridge_url,
        "paper_guard": "local_bridge_endpoint",
        "write_guard": "read_only_profile",
    }
    if missing:
        report["error"] = f"{label} connector not configured: missing {', '.join(missing)}."
        return report
    payload = _bridge_get(config, "/health", client=client)
    if _payload_ok(payload):
        report["bridge"] = payload
        return report
    report["status"] = "error"
    report["error"] = str(payload.get("error") or payload.get("message") or f"{label} bridge health check failed.")
    report["bridge"] = payload
    return report


def get_account_snapshot(config: KoreanConnectorConfig, *, label: str, client: Any | None = None) -> dict[str, Any]:
    return _read_endpoint(config, "/account", label=label, client=client)


def get_positions(config: KoreanConnectorConfig, *, label: str, client: Any | None = None) -> dict[str, Any]:
    return _read_endpoint(config, "/positions", label=label, client=client)


def get_open_orders(
    config: KoreanConnectorConfig,
    *,
    label: str,
    include_executions: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    return _read_endpoint(
        config,
        "/orders",
        label=label,
        params={"include_executions": "true" if include_executions else "false"},
        client=client,
    )


def get_quote(symbol: str, *, config: KoreanConnectorConfig, label: str, client: Any | None = None) -> dict[str, Any]:
    clean = _normalize_kr_symbol(symbol)
    return _read_endpoint(config, f"/quote/{quote(clean)}", label=label, client=client, extras={"symbol": clean})


def get_historical_bars(
    symbol: str,
    *,
    config: KoreanConnectorConfig,
    label: str,
    period: str = "1d",
    limit: int = 90,
    client: Any | None = None,
) -> dict[str, Any]:
    clean = _normalize_kr_symbol(symbol)
    return _read_endpoint(
        config,
        f"/history/{quote(clean)}",
        label=label,
        params={"period": period, "limit": str(int(limit))},
        client=client,
        extras={"symbol": clean, "period": period},
    )


def _read_endpoint(
    config: KoreanConnectorConfig,
    path: str,
    *,
    label: str,
    params: Mapping[str, Any] | None = None,
    client: Any | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    missing = _missing_bridge_fields(config)
    if missing:
        return _not_configured(config, label=label, missing=missing)
    payload = _bridge_get(config, path, params=params, client=client)
    if not _payload_ok(payload):
        return {
            "status": "error",
            "profile": config.profile,
            "connector": config.connector,
            "error": str(payload.get("error") or payload.get("message") or f"{label} bridge request failed."),
            "raw": payload,
            **dict(extras or {}),
        }
    return {
        "profile": config.profile,
        "connector": config.connector,
        "transport": "local_bridge",
        **dict(extras or {}),
        **payload,
    }


def _bridge_get(
    config: KoreanConnectorConfig,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    with _client(config, client) as active:
        response = active.get(
            config.bridge_url.rstrip("/") + path,
            params=dict(params or {}),
            headers=_headers(config),
            timeout=config.timeout,
        )
        return _response_json(response)


@contextmanager
def _client(config: KoreanConnectorConfig, client: Any | None = None) -> Iterator[Any]:
    if client is not None:
        yield client
        return
    try:
        import httpx  # type: ignore
    except ImportError as exc:
        raise KoreanConnectorConfigError("Korean local bridge calls require httpx; install project dependencies first.") from exc
    with httpx.Client(timeout=config.timeout, follow_redirects=True, trust_env=True) as active:
        yield active


def _headers(config: KoreanConnectorConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.bridge_token}",
        "X-Vibe-Connector": config.connector,
        "X-Vibe-Transport": "local_bridge",
    }


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    payload = response.json()
    return dict(payload or {}) if isinstance(payload, Mapping) else {"raw": payload}


def _payload_ok(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("status", "ok")).lower() == "ok"


def _missing_bridge_fields(config: KoreanConnectorConfig) -> list[str]:
    missing = []
    if not config.bridge_url:
        missing.append("bridge_url")
    if not config.bridge_token:
        missing.append("bridge_token")
    return missing


def _not_configured(config: KoreanConnectorConfig, *, label: str, missing: list[str]) -> dict[str, Any]:
    return {
        "status": "error",
        "profile": config.profile,
        "connector": config.connector,
        "error": f"{label} connector not configured: missing {', '.join(missing)}.",
    }


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
