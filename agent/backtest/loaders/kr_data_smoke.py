"""Credential-gated smoke checks for official Korean market data sources."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import os
from typing import Any

from backtest.loaders.koscom import DataLoader as KoscomDataLoader
from backtest.loaders.krx import DataLoader as KrxDataLoader

DEFAULT_SYMBOL = "005930.KS"
DEFAULT_START_DATE = "2026-01-02"
DEFAULT_END_DATE = "2026-01-02"
DEFAULT_NATION_CODE = "KR"
DEFAULT_OPERATIONS = ("krx_daily", "koscom_daily", "koscom_holidays")

_OPERATION_SOURCE = {
    "krx_daily": "krx",
    "koscom_daily": "koscom",
    "koscom_holidays": "koscom",
}
_SOURCE_ENV_KEYS = {
    "krx": ("KRX_OPEN_API_AUTH_KEY", "VIBE_TRADING_KRX_AUTH_KEY"),
    "koscom": (
        "KOSCOM_OPEN_API_KEY",
        "KOSCOM_CHECK_API_KEY",
        "VIBE_TRADING_KOSCOM_API_KEY",
    ),
}
_DEFAULT_LOADER_FACTORIES: dict[str, Callable[[], Any]] = {
    "krx": KrxDataLoader,
    "koscom": KoscomDataLoader,
}


def build_smoke_plan(
    *,
    operations: Iterable[str] | None = None,
    symbol: str = DEFAULT_SYMBOL,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    nation_code: str = DEFAULT_NATION_CODE,
    loader_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """Return the read-only Korean data-source checks that would be executed."""
    selected = _normalize_operations(operations)
    factories = _resolve_loader_factories(loader_factories)
    sources = sorted({_OPERATION_SOURCE[operation] for operation in selected})
    loaders: dict[str, Any] = {}

    return {
        "status": "planned",
        "allow_data_calls_required": True,
        "read_only": True,
        "sources": [
            {
                "source": source,
                "configured": _loader_available(source, factories, loaders),
                "required_env": list(_SOURCE_ENV_KEYS[source]),
            }
            for source in sources
        ],
        "steps": [
            _plan_step(
                operation,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                nation_code=nation_code,
            )
            for operation in selected
        ],
    }


def run_smoke(
    *,
    allow_data_calls: bool = False,
    operations: Iterable[str] | None = None,
    symbol: str = DEFAULT_SYMBOL,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    nation_code: str = DEFAULT_NATION_CODE,
    loader_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """Execute explicitly allowed read-only checks against KRX/Koscom loaders."""
    selected = _normalize_operations(operations)
    factories = _resolve_loader_factories(loader_factories)
    plan = build_smoke_plan(
        operations=selected,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        nation_code=nation_code,
        loader_factories=factories,
    )
    if not allow_data_calls:
        return {
            "status": "not_run",
            "reason": "allow_data_calls_required",
            "plan": plan,
            "checks": [],
        }

    loaders: dict[str, Any] = {}
    checks = [
        _run_operation(
            operation,
            factories=factories,
            loaders=loaders,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            nation_code=nation_code,
        )
        for operation in selected
    ]
    return {
        "status": _overall_status(checks),
        "plan": plan,
        "checks": checks,
    }


def _normalize_operations(operations: Iterable[str] | None) -> list[str]:
    selected = list(operations or DEFAULT_OPERATIONS)
    unsupported = [operation for operation in selected if operation not in _OPERATION_SOURCE]
    if unsupported:
        raise ValueError(f"unsupported smoke operation(s): {', '.join(sorted(unsupported))}")
    return selected


def _resolve_loader_factories(
    loader_factories: Mapping[str, Callable[[], Any]] | None,
) -> dict[str, Callable[[], Any]]:
    factories = dict(_DEFAULT_LOADER_FACTORIES)
    if loader_factories:
        factories.update(loader_factories)
    return factories


def _plan_step(
    operation: str,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    nation_code: str,
) -> dict[str, Any]:
    source = _OPERATION_SOURCE[operation]
    step: dict[str, Any] = {
        "operation": operation,
        "source": source,
        "read_only": True,
    }
    if operation.endswith("_daily"):
        step.update(
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "interval": "1D",
            }
        )
    else:
        step["nation_code"] = nation_code.upper()
    return step


def _run_operation(
    operation: str,
    *,
    factories: Mapping[str, Callable[[], Any]],
    loaders: dict[str, Any],
    symbol: str,
    start_date: str,
    end_date: str,
    nation_code: str,
) -> dict[str, Any]:
    source = _OPERATION_SOURCE[operation]
    loader = _loader_for(source, factories, loaders)
    if not _is_available(loader):
        return {
            "operation": operation,
            "source": source,
            "status": "blocked",
            "reason": "credential_not_configured",
        }

    try:
        if operation.endswith("_daily"):
            data = loader.fetch([symbol], start_date, end_date, interval="1D")
            return {
                "operation": operation,
                "source": source,
                "status": "passed",
                "symbol": symbol,
                "rows": _row_count(data),
            }
        holidays = loader.fetch_holidays(nation_code=nation_code.upper())
        return {
            "operation": operation,
            "source": source,
            "status": "passed",
            "nation_code": nation_code.upper(),
            "holiday_count": len(holidays),
        }
    except Exception as exc:  # pragma: no cover - exercised through real smoke runs
        return {
            "operation": operation,
            "source": source,
            "status": "error",
            "error": type(exc).__name__,
            "message": _scrub_secrets(str(exc)),
        }


def _loader_available(
    source: str,
    factories: Mapping[str, Callable[[], Any]],
    loaders: dict[str, Any],
) -> bool:
    try:
        return _is_available(_loader_for(source, factories, loaders))
    except Exception:
        return False


def _loader_for(
    source: str,
    factories: Mapping[str, Callable[[], Any]],
    loaders: dict[str, Any],
) -> Any:
    if source not in loaders:
        loaders[source] = factories[source]()
    return loaders[source]


def _is_available(loader: Any) -> bool:
    is_available = getattr(loader, "is_available", None)
    return bool(is_available()) if callable(is_available) else True


def _row_count(data: Mapping[str, Any]) -> int:
    total = 0
    for frame in data.values():
        total += len(frame)
    return total


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks}
    if "error" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    return "passed"


def _scrub_secrets(value: str) -> str:
    scrubbed = value
    for keys in _SOURCE_ENV_KEYS.values():
        for key in keys:
            secret = os.getenv(key, "").strip()
            if secret:
                scrubbed = scrubbed.replace(secret, "<redacted>")
    return scrubbed
