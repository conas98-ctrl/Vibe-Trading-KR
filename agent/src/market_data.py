"""Shared market data helpers for MCP and local agent tools."""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 250
KR_DERIVED_WINDOWS = (20, 60, 120, 200)
_YFINANCE_FUNDAMENTAL_FIELDS = {
    "PER": ("trailingPE", "trailing"),
    "PBR": ("priceToBook", None),
    "EPS": ("trailingEps", "trailing"),
    "BPS": ("bookValue", None),
}

_KR_EXPLICIT_PATTERN = re.compile(
    r"^(?:\d{6}\.(?:KS|KQ)|(?:KRX|KOSPI|KOSDAQ):\d{6})$", re.I
)
_KR_BARE_PATTERN = re.compile(r"^\d{6}$")

_SOURCE_PATTERNS = [
    (re.compile(r"^\d{6}\.(SZ|SH|BJ)$", re.I), "tushare"),
    (re.compile(r"^[A-Z]+\.US$", re.I), "yfinance"),
    (re.compile(r"^\d{3,5}\.HK$", re.I), "yfinance"),
    (re.compile(r"^[A-Z]+-USDT$", re.I), "okx"),
    (re.compile(r"^[A-Z]+/USDT$", re.I), "ccxt"),
]


def detect_source(code: str) -> str:
    """Infer the best loader source for a normalized symbol."""
    for pattern, source in _SOURCE_PATTERNS:
        if pattern.match(code):
            return source
    return "tushare"


def is_korean_equity(code: str, *, market: str = "auto") -> bool:
    """Identify unambiguous Korean symbols, or bare tickers with an explicit hint."""
    symbol = str(code).strip()
    if _KR_EXPLICIT_PATTERN.fullmatch(symbol):
        return True
    return market.lower() == "kr" and bool(_KR_BARE_PATTERN.fullmatch(symbol))


def normalize_korean_ticker(code: str) -> str:
    """Convert a supported Korean symbol to the six-digit pykrx ticker."""
    symbol = str(code).strip().upper()
    if symbol.endswith((".KS", ".KQ")):
        symbol = symbol[:-3]
    for prefix in ("KRX:", "KOSPI:", "KOSDAQ:"):
        if symbol.startswith(prefix):
            symbol = symbol[len(prefix):]
            break
    if not _KR_BARE_PATTERN.fullmatch(symbol):
        raise ValueError(f"Unsupported Korean equity symbol: {code}")
    return symbol


def discover_pykrx_tools() -> dict[str, Any]:
    """Discover configured pykrx MCP wrappers keyed by remote tool metadata."""
    from src.config.loader import load_agent_config
    from src.tools.mcp import build_mcp_tool_wrappers

    server = load_agent_config().mcp_servers.get("pykrx")
    if server is None:
        return {}
    return {tool._spec.remote_name: tool for tool in build_mcp_tool_wrappers("pykrx", server)}


def _call_remote_tool(tool: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    result = tool.execute(**arguments) if hasattr(tool, "execute") else tool(**arguments)
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, dict):
        raise ValueError("pykrx MCP returned a non-object response")
    return result


def _unwrap_mcp_data(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") == "error" or payload.get("isError") is True:
        raise ValueError(str(payload.get("error") or payload.get("text") or "pykrx MCP error"))
    candidates = [payload.get("data"), payload.get("structured_content"), payload]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("result", "data"):
                nested = candidate.get(key)
                if isinstance(nested, dict) and ("data" in nested or "error" in nested):
                    candidate = nested
                    break
            if candidate.get("error"):
                raise ValueError(str(candidate["error"]))
            if isinstance(candidate.get("data"), list):
                return candidate
    text = payload.get("text")
    if isinstance(text, str):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            if decoded.get("error"):
                raise ValueError(str(decoded["error"]))
            if isinstance(decoded.get("data"), list):
                return decoded
    raise ValueError("pykrx MCP returned no tabular data")


def _unwrap_mcp_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    """Unwrap an MCP response whose data payload is keyed rather than row-based."""
    if payload.get("status") == "error" or payload.get("isError") is True:
        raise ValueError(str(payload.get("error") or payload.get("text") or "pykrx MCP error"))
    candidates: list[Any] = [payload.get("data"), payload]
    text = payload.get("text")
    if isinstance(text, str):
        try:
            candidates.append(json.loads(text))
        except json.JSONDecodeError:
            pass
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("error"):
            raise ValueError(str(candidate["error"]))
        nested = candidate.get("data")
        if isinstance(nested, dict) and nested:
            return nested
    raise ValueError("pykrx MCP returned no keyed data")


_OHLCV_ALIASES = {
    "date": {"date", "trade_date", "날짜"},
    "open": {"open", "시가"},
    "high": {"high", "고가"},
    "low": {"low", "저가"},
    "close": {"close", "종가"},
    "volume": {"volume", "거래량"},
}


def _normalize_pykrx_ohlcv(payload: dict[str, Any]) -> pd.DataFrame:
    body = _unwrap_mcp_data(payload)
    rows = body.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("pykrx MCP returned empty OHLCV data")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lowered = {str(key).strip().lower(): value for key, value in row.items()}
        item: dict[str, Any] = {}
        for target, aliases in _OHLCV_ALIASES.items():
            for alias in aliases:
                if alias.lower() in lowered:
                    item[target] = lowered[alias.lower()]
                    break
        if set(item) != set(_OHLCV_ALIASES):
            continue
        try:
            date = pd.to_datetime(item.pop("date"), errors="raise")
            numeric = {key: float(str(value).replace(",", "")) for key, value in item.items()}
        except (TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in numeric.values()):
            normalized.append({"date": date, **numeric})
    if not normalized:
        raise ValueError("pykrx MCP OHLCV rows lack valid date/open/high/low/close/volume values")
    frame = pd.DataFrame(normalized).set_index("date").sort_index()
    frame.index.name = "date"
    return frame.loc[~frame.index.duplicated(keep="last")]


def _derived_from_pykrx(
    frame: pd.DataFrame, *, requested_start: str, requested_end: str,
) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    computed_from_close = {
        "source": "computed", "computed_from": "ohlcv.close",
        "upstream_source": "pykrx_mcp",
    }
    computed_from_volume = {
        "source": "computed", "computed_from": "ohlcv.volume",
        "upstream_source": "pykrx_mcp",
    }
    for window in KR_DERIVED_WINDOWS:
        name = f"ma{window}"
        latest[name] = _json_safe(frame["close"].rolling(window).mean().iloc[-1])
        provenance[name] = dict(computed_from_close)

    latest_date = frame.index[-1]
    return_anchors = {
        "return_1w": latest_date - pd.Timedelta(days=7),
        "return_1m": latest_date - pd.DateOffset(months=1),
        "return_3m": latest_date - pd.DateOffset(months=3),
        "return_6m": latest_date - pd.DateOffset(months=6),
    }
    for name, anchor in return_anchors.items():
        history = frame.loc[frame.index <= anchor, "close"]
        latest[name] = (
            _json_safe(frame["close"].iloc[-1] / history.iloc[-1] - 1)
            if not history.empty
            else None
        )
        provenance[name] = dict(computed_from_close)

    requested_frame = frame.loc[
        (frame.index >= pd.Timestamp(requested_start))
        & (frame.index <= pd.Timestamp(requested_end))
    ]
    latest["period_return"] = (
        _json_safe(requested_frame["close"].iloc[-1] / requested_frame["close"].iloc[0] - 1)
        if len(requested_frame) > 1
        else None
    )
    provenance["period_return"] = dict(computed_from_close)

    for window in (20, 60, 120):
        name = f"volume_average_{window}d"
        latest[name] = _json_safe(frame["volume"].rolling(window).mean().iloc[-1])
        provenance[name] = dict(computed_from_volume)
    period_volume_average = (
        _json_safe(requested_frame["volume"].mean()) if not requested_frame.empty else None
    )
    latest["period_volume_average"] = period_volume_average
    latest["volume_average"] = period_volume_average
    provenance["period_volume_average"] = dict(computed_from_volume)
    provenance["volume_average"] = {
        **computed_from_volume, "alias_of": "period_volume_average",
    }

    daily_returns = requested_frame["close"].pct_change().dropna()
    latest["volatility_annualized"] = _json_safe(
        daily_returns.std(ddof=1) * math.sqrt(252)
    )
    provenance["volatility_annualized"] = {
        "source": "computed", "computed_from": "ohlcv.close.pct_change",
        "upstream_source": "pykrx_mcp", "annualization_factor": 252,
        "estimator": "sample_std",
    }
    return {"values": latest, "provenance": provenance}


def _failure_provenance(error: Exception) -> dict[str, Any]:
    return {
        "source": "unavailable", "fallback": False, "status": "unavailable",
        "primary_failure": str(error),
    }


def _valid_number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number != 0 else None


def _latest_row(body: dict[str, Any]) -> dict[str, Any]:
    rows = body.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("pykrx MCP returned empty data")
    row = rows[-1]
    if not isinstance(row, dict):
        raise ValueError("pykrx MCP returned a malformed latest row")
    return row


def _pick_number(row: dict[str, Any], *aliases: str) -> float | None:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        if alias.lower() in lowered:
            return _valid_number(lowered[alias.lower()])
    return None


def _yfinance_symbol_for_korean(code: str) -> str | None:
    """Return a Yahoo symbol only when the Korean board is explicit."""
    upper = str(code).strip().upper()
    if upper.endswith((".KS", ".KQ")):
        return upper
    if upper.startswith("KOSPI:"):
        return f"{upper.removeprefix('KOSPI:').zfill(6)}.KS"
    if upper.startswith("KOSDAQ:"):
        return f"{upper.removeprefix('KOSDAQ:').zfill(6)}.KQ"
    return None


def _fetch_yfinance_info(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    info = yf.Ticker(symbol).info
    if not isinstance(info, dict):
        raise ValueError("yfinance Ticker.info returned a non-object response")
    return info


def _field_failure(reason: str) -> dict[str, Any]:
    return {
        "source": "unavailable", "fallback": False, "status": "unavailable",
        "primary_failure": reason,
    }


def fetch_korean_market_data(
    *, codes: list[str], start_date: str, end_date: str,
    max_rows: int = DEFAULT_MAX_ROWS, fields: list[str] | None = None,
    mcp_tools: dict[str, Any] | None = None,
    fallback_resolvers: dict[str, Callable[..., dict[str, Any]]] | None = None,
    yfinance_info_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch Korean analysis data with pykrx OHLCV locked against fallback writes."""
    requested = set(fields or ("ohlcv", "derived", "fundamentals", "market_cap", "investor_flow"))
    tools = mcp_tools if mcp_tools is not None else discover_pykrx_tools()
    fallback_resolvers = fallback_resolvers or {}
    yfinance_info_resolver = yfinance_info_resolver or _fetch_yfinance_info
    output: dict[str, Any] = {}
    for original in codes:
        ticker = normalize_korean_ticker(original)
        # Keep the compact, decision-critical fields before the potentially large
        # OHLCV payload.  The agent loop clips tool results by character count, so
        # insertion order is part of the LLM-facing contract here.
        result: dict[str, Any] = {
            "symbol": original,
            "ticker": ticker,
            "as_of": None,
            "latest_ohlcv": None,
        }
        if "derived" in requested:
            result["derived"] = None
        result["provenance"] = {}
        ohlcv_frame: pd.DataFrame | None = None
        ohlcv_output: list[dict[str, Any]] | dict[str, object] | None = None
        yahoo_info: dict[str, Any] | None = None
        yahoo_error: str | None = None

        def get_yfinance_info_once() -> dict[str, Any] | None:
            nonlocal yahoo_info, yahoo_error
            if yahoo_info is not None or yahoo_error is not None:
                return yahoo_info
            yahoo_symbol = _yfinance_symbol_for_korean(original)
            if yahoo_symbol is None:
                yahoo_error = "KOSPI/KOSDAQ board is not explicit; yfinance fallback skipped"
                return None
            try:
                yahoo_info = yfinance_info_resolver(yahoo_symbol)
                if not isinstance(yahoo_info, dict):
                    raise ValueError("yfinance Ticker.info returned a non-object response")
            except Exception as exc:
                yahoo_info = None
                yahoo_error = str(exc)
            return yahoo_info
        try:
            tool = tools.get("get_stock_ohlcv")
            if tool is None:
                raise ValueError("configured pykrx MCP does not expose get_stock_ohlcv")
            requested_start = pd.Timestamp(start_date)
            expanded_start = min(requested_start, pd.Timestamp(end_date) - timedelta(days=400))
            payload = _call_remote_tool(tool, {
                "ticker": ticker, "start_date": expanded_start.strftime("%Y%m%d"),
                "end_date": pd.Timestamp(end_date).strftime("%Y%m%d"), "adjusted": True,
            })
            ohlcv_frame = _normalize_pykrx_ohlcv(payload)
            records = [
                {key: _json_safe(value) for key, value in row.items()}
                for row in ohlcv_frame.reset_index().to_dict(orient="records")
            ]
            result["as_of"] = ohlcv_frame.index[-1].date().isoformat()
            result["latest_ohlcv"] = {**records[-1], "date": result["as_of"]}
            ohlcv_output = cap_rows(records, max_rows)
            result["provenance"]["ohlcv"] = {"source": "pykrx_mcp", "fallback": False, "status": "ok"}
        except Exception as exc:
            # No generic price fallback: Korean OHLCV failure remains explicit.
            result["provenance"]["ohlcv"] = _failure_provenance(exc)

        if "derived" in requested:
            if ohlcv_frame is not None:
                derived = _derived_from_pykrx(
                    ohlcv_frame, requested_start=start_date, requested_end=end_date,
                )
                result["derived"] = derived["values"]
                result["provenance"]["derived"] = derived["provenance"]
            else:
                result["derived"] = None
                result["provenance"]["derived"] = _failure_provenance(
                    ValueError("pykrx OHLCV unavailable; derived indicators were not computed")
                )

        if "fundamentals" in requested:
            fundamental_values: dict[str, float | None] = {}
            field_provenance: dict[str, dict[str, Any]] = {}
            primary_failure = ""
            try:
                tool = tools.get("get_market_fundamental_by_date")
                if tool is None:
                    raise ValueError("configured pykrx MCP does not expose get_market_fundamental_by_date")
                body = _unwrap_mcp_data(_call_remote_tool(tool, {
                    "ticker": ticker, "start_date": pd.Timestamp(start_date).strftime("%Y%m%d"),
                    "end_date": pd.Timestamp(end_date).strftime("%Y%m%d"),
                }))
                row = _latest_row(body)
            except Exception as exc:
                row = {}
                primary_failure = str(exc)
            for field, (provider_field, basis) in _YFINANCE_FUNDAMENTAL_FIELDS.items():
                value = _pick_number(row, field)
                if value is not None:
                    fundamental_values[field] = value
                    field_provenance[field] = {
                        "source": "pykrx_mcp", "fallback": False, "status": "ok",
                    }
                    continue
                reason = primary_failure or f"pykrx returned no valid {field}"
                info = get_yfinance_info_once()
                fallback_value = _valid_number(info.get(provider_field)) if info is not None else None
                if fallback_value is None:
                    fundamental_values[field] = None
                    field_provenance[field] = _field_failure(
                        f"{reason}; yfinance fallback unavailable: {yahoo_error or provider_field + ' missing'}"
                    )
                    continue
                fundamental_values[field] = fallback_value
                provenance = {
                    "source": "yfinance", "provider_field": provider_field,
                    "as_of_type": "current_snapshot", "fallback": True, "status": "ok",
                    "primary_failure": reason,
                }
                if basis:
                    provenance["basis"] = basis
                field_provenance[field] = provenance
            result["fundamentals"] = fundamental_values
            sources = {item["source"] for item in field_provenance.values()}
            result["provenance"]["fundamentals"] = {
                "source": sources.pop() if len(sources) == 1 else "mixed",
                "fallback": any(item.get("fallback") is True for item in field_provenance.values()),
                "status": "ok" if any(item["status"] == "ok" for item in field_provenance.values()) else "unavailable",
                "fields": field_provenance,
            }

        if "market_cap" in requested:
            market_cap_value: float | None = None
            primary_failure = ""
            try:
                tool = tools.get("get_market_cap_by_date")
                if tool is None:
                    raise ValueError("configured pykrx MCP does not expose get_market_cap_by_date")
                body = _unwrap_mcp_data(_call_remote_tool(tool, {
                    "ticker": ticker, "start_date": pd.Timestamp(start_date).strftime("%Y%m%d"),
                    "end_date": pd.Timestamp(end_date).strftime("%Y%m%d"),
                }))
                market_cap_value = _pick_number(_latest_row(body), "market_cap", "시가총액")
                if market_cap_value is None:
                    raise ValueError("pykrx returned no valid market cap")
            except Exception as exc:
                primary_failure = str(exc)
            if market_cap_value is not None:
                result["market_cap"] = market_cap_value
                result["provenance"]["market_cap"] = {
                    "source": "pykrx_mcp", "fallback": False, "status": "ok",
                }
            else:
                info = get_yfinance_info_once()
                fallback_value = _valid_number(info.get("marketCap")) if info is not None else None
                if fallback_value is None:
                    result["market_cap"] = None
                    result["provenance"]["market_cap"] = _field_failure(
                        f"{primary_failure}; yfinance fallback unavailable: {yahoo_error or 'marketCap missing'}"
                    )
                else:
                    result["market_cap"] = fallback_value
                    result["provenance"]["market_cap"] = {
                        "source": "yfinance", "provider_field": "marketCap",
                        "as_of_type": "current_snapshot", "fallback": True, "status": "ok",
                        "primary_failure": primary_failure,
                    }

        if "investor_flow" in requested:
            flow_result: dict[str, Any] = {}
            flow_provenance: dict[str, Any] = {}
            for kind, remote_name in (
                ("volume", "get_market_trading_volume_by_investor"),
                ("value", "get_market_trading_value_by_investor"),
            ):
                try:
                    tool = tools.get(remote_name)
                    if tool is None:
                        raise ValueError(f"configured pykrx MCP does not expose {remote_name}")
                    flow_result[kind] = _unwrap_mcp_mapping(_call_remote_tool(tool, {
                        "ticker": ticker, "start_date": pd.Timestamp(start_date).strftime("%Y%m%d"),
                        "end_date": pd.Timestamp(end_date).strftime("%Y%m%d"),
                    }))
                    flow_provenance[kind] = {
                        "source": "pykrx_mcp", "fallback": False, "status": "ok",
                    }
                except Exception as exc:
                    flow_result[kind] = None
                    flow_provenance[kind] = _failure_provenance(exc)
            result["investor_flow"] = flow_result
            result["provenance"]["investor_flow"] = {
                "source": "pykrx_mcp" if any(v["status"] == "ok" for v in flow_provenance.values()) else "unavailable",
                "fallback": False,
                "status": "ok" if any(v["status"] == "ok" for v in flow_provenance.values()) else "unavailable",
                "parts": flow_provenance,
            }
        # Append the large series last so summary/derived/provenance survive the
        # agent loop's tool-result character limit. Internal calculations above
        # always use the complete normalized DataFrame.
        result["ohlcv"] = ohlcv_output
        output[original] = result
    return output


def get_loader(source: str):
    """Get loader class via registry with fallback support."""
    from backtest.loaders.registry import get_loader_cls_with_fallback

    return get_loader_cls_with_fallback(source)


def cap_rows(records: list, max_rows: int) -> list | dict[str, object]:
    """Bound a per-symbol row list to keep tool payloads within budget."""
    n = len(records)
    if max_rows < 0:
        max_rows = DEFAULT_MAX_ROWS
    if max_rows == 0 or n <= max_rows:
        return records
    step = math.ceil(n / max_rows)
    sampled = records[::step]
    if sampled[-1] is not records[-1]:
        sampled = sampled + [records[-1]]
    return {
        "rows": n,
        "returned": len(sampled),
        "truncated": True,
        "policy": f"every-{step}th-row (even stride; last bar pinned)",
        "hint": "narrow the date range, coarsen interval, or set max_rows=0 for all rows",
        "data": sampled,
    }


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def fetch_market_data(
    *,
    codes: list[str],
    start_date: str,
    end_date: str,
    source: str = "auto",
    interval: str = "1D",
    max_rows: int = DEFAULT_MAX_ROWS,
    market: str = "auto",
    fields: list[str] | None = None,
    loader_resolver: Callable[[str], type] = get_loader,
    mcp_tools: dict[str, Any] | None = None,
    fallback_resolvers: dict[str, Callable[..., dict[str, Any]]] | None = None,
    yfinance_info_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch normalized OHLCV data through the repository loader layer."""
    kr_codes = [code for code in codes if is_korean_equity(code, market=market)]
    if kr_codes:
        if len(kr_codes) != len(codes):
            raise ValueError("Do not mix Korean-policy symbols with other markets in one get_market_data call")
        if str(interval or "1D").upper() != "1D":
            raise ValueError("pykrx MCP Korean analysis currently supports daily OHLCV only")
        return fetch_korean_market_data(
            codes=kr_codes, start_date=start_date, end_date=end_date, max_rows=max_rows,
            fields=fields, mcp_tools=mcp_tools, fallback_resolvers=fallback_resolvers,
            yfinance_info_resolver=yfinance_info_resolver,
        )
    results: dict[str, Any] = {}

    if source == "auto":
        groups: dict[str, list[str]] = {}
        for code in codes:
            src = detect_source(code)
            groups.setdefault(src, []).append(code)
    else:
        groups = {source: list(codes)}

    for src, src_codes in groups.items():
        loader_cls = loader_resolver(src)
        loader = loader_cls()
        try:
            data_map = loader.fetch(src_codes, start_date, end_date, interval=interval)
        except Exception:
            logger.exception(
                "market-data loader %r failed for %s; codes fall through to _unresolved",
                src,
                src_codes,
            )
            data_map = {}
        for symbol, df in data_map.items():
            records = df.reset_index().to_dict(orient="records")
            for row in records:
                for key, value in row.items():
                    row[key] = _json_safe(value)
            results[symbol] = cap_rows(records, max_rows)

    unresolved = [code for code in codes if code not in results]
    if unresolved:
        results["_unresolved"] = unresolved

    return results


def fetch_market_data_json(**kwargs: Any) -> str:
    """Fetch market data and return strict JSON."""
    return json.dumps(fetch_market_data(**kwargs), ensure_ascii=False, indent=2, allow_nan=False)
