"""Credential-gated smoke runner for Korean broker connectors."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Callable

from src.trading import profiles, service
from src.trading.types import TradingProfile

DEFAULT_SYMBOL = "005930"
DEFAULT_OPERATIONS = ("check", "quote")
KOREAN_CONNECTORS = frozenset({"kis", "ls", "db", "kiwoom", "kiwoom-openapi", "daishin-cybos"})

_READ_OPERATION_CAPABILITIES = {
    "account": "account.read",
    "positions": "positions.read",
    "orders": "orders.read",
    "quote": "quotes.read",
    "history": "history.read",
}


def build_smoke_plan(
    *,
    profile_ids: Iterable[str] | None = None,
    include_trade_profiles: bool = False,
    operations: Sequence[str] = DEFAULT_OPERATIONS,
    symbol: str = DEFAULT_SYMBOL,
) -> dict[str, Any]:
    """Return the Korean connector smoke plan without touching broker APIs."""

    selected = _select_profiles(profile_ids=profile_ids, include_trade_profiles=include_trade_profiles)
    requested_ops = _normalize_operations(operations)
    return {
        "status": "planned",
        "symbol": str(symbol or DEFAULT_SYMBOL).strip() or DEFAULT_SYMBOL,
        "allow_broker_calls_required": True,
        "allow_live_required": any(profile.environment == "live" for profile in selected),
        "profiles": [_profile_plan(profile, requested_ops) for profile in selected],
    }


def run_smoke(
    *,
    profile_ids: Iterable[str] | None = None,
    include_trade_profiles: bool = False,
    operations: Sequence[str] = DEFAULT_OPERATIONS,
    symbol: str = DEFAULT_SYMBOL,
    allow_broker_calls: bool = False,
    allow_live: bool = False,
) -> dict[str, Any]:
    """Run read-only Korean broker smoke checks after explicit opt-in.

    The function is intentionally fail-closed: the default call only reports the
    plan. It never places or cancels orders, and live profiles require a second
    explicit ``allow_live=True`` opt-in in addition to ``allow_broker_calls``.
    """

    plan = build_smoke_plan(
        profile_ids=profile_ids,
        include_trade_profiles=include_trade_profiles,
        operations=operations,
        symbol=symbol,
    )
    if not allow_broker_calls:
        return {
            **plan,
            "status": "not_run",
            "reason": "Korean broker smoke requires allow_broker_calls=True before any credentialed API call.",
            "profiles": [{**row, "status": "not_run", "steps": []} for row in plan["profiles"]],
        }

    rows: list[dict[str, Any]] = []
    for row in plan["profiles"]:
        profile = profiles.profile_by_id(row["profile_id"])
        if profile.environment == "live" and not allow_live:
            rows.append(
                {
                    **row,
                    "status": "blocked",
                    "reason": "Live Korean broker smoke requires allow_live=True.",
                    "steps": [],
                }
            )
            continue
        rows.append(_run_profile(profile, row["operations"], symbol=plan["symbol"]))

    status = _aggregate_status(rows)
    result = {**plan, "status": status, "profiles": rows}
    if status == "blocked":
        result["reason"] = "One or more live Korean broker profiles require allow_live=True."
    return result


def _select_profiles(
    *,
    profile_ids: Iterable[str] | None,
    include_trade_profiles: bool,
) -> list[TradingProfile]:
    if profile_ids is not None:
        return [profiles.profile_by_id(profile_id) for profile_id in profile_ids]
    selected = [
        profile
        for profile in profiles.list_profiles()
        if profile.connector in KOREAN_CONNECTORS and (include_trade_profiles or profile.readonly)
    ]
    return sorted(selected, key=lambda profile: profile.id)


def _profile_plan(profile: TradingProfile, requested_ops: tuple[str, ...]) -> dict[str, Any]:
    return {
        "profile_id": profile.id,
        "connector": profile.connector,
        "environment": profile.environment,
        "transport": profile.transport,
        "readonly": profile.readonly,
        "operations": [operation for operation in requested_ops if _profile_supports_operation(profile, operation)],
        "credential_gate": "allow_broker_calls=True",
        "live_gate": "allow_live=True" if profile.environment == "live" else None,
    }


def _profile_supports_operation(profile: TradingProfile, operation: str) -> bool:
    if operation == "check":
        return True
    capability = _READ_OPERATION_CAPABILITIES[operation]
    return capability in profile.capabilities


def _normalize_operations(operations: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for operation in operations:
        token = str(operation or "").strip().lower()
        if not token:
            continue
        if token == "orders.place":
            raise ValueError("Korean credential smoke is read-only and never runs orders.place")
        if token not in {"check", *_READ_OPERATION_CAPABILITIES}:
            raise ValueError(f"unsupported Korean credential smoke operation: {operation!r}")
        if token not in normalized:
            normalized.append(token)
    return tuple(normalized or DEFAULT_OPERATIONS)


def _run_profile(profile: TradingProfile, operations: Sequence[str], *, symbol: str) -> dict[str, Any]:
    steps = [_run_operation(profile.id, operation, symbol=symbol) for operation in operations]
    return {
        "profile_id": profile.id,
        "connector": profile.connector,
        "environment": profile.environment,
        "transport": profile.transport,
        "readonly": profile.readonly,
        "operations": list(operations),
        "status": _aggregate_status(steps),
        "steps": steps,
    }


def _run_operation(profile_id: str, operation: str, *, symbol: str) -> dict[str, Any]:
    calls: dict[str, Callable[..., dict[str, Any]]] = {
        "check": service.check_connection,
        "account": service.get_account,
        "positions": service.get_positions,
        "orders": service.get_open_orders,
        "quote": lambda target_profile: service.get_quote(symbol, target_profile),
        "history": lambda target_profile: service.get_history(symbol, target_profile),
    }
    try:
        payload = calls[operation](profile_id)
    except Exception as exc:  # noqa: BLE001 - smoke report must survive connector raises
        payload = {"status": "error", "error": str(exc), "profile_id": profile_id}
    step = dict(payload)
    step["operation"] = operation
    return step


def _aggregate_status(rows: Sequence[dict[str, Any]]) -> str:
    statuses = {str(row.get("status") or "").lower() for row in rows}
    if not rows:
        return "empty"
    if "error" in statuses:
        return "error"
    if "blocked" in statuses:
        return "blocked"
    if "not_run" in statuses:
        return "not_run"
    if statuses <= {"ok"}:
        return "ok"
    return "partial"
