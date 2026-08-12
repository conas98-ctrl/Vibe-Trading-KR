from __future__ import annotations

import json

import pandas as pd

from src.agent.context import _SYSTEM_PROMPT
from src.market_data import fetch_market_data, fetch_market_data_json, is_korean_equity
from src.swarm.models import SwarmAgentSpec
from src.swarm.presets import list_presets, load_preset
from src.swarm.worker import build_worker_prompt
from src.tools import build_swarm_registry


def test_market_data_json_is_strict_when_loader_returns_nan():
    idx = pd.date_range("2026-01-01", periods=1, freq="D")
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [float("nan")],
            "low": [0.9],
            "close": [1.1],
            "volume": [100],
        },
        index=idx,
    )
    df.index.name = "trade_date"

    class _Loader:
        def fetch(self, codes, start, end, interval="1D"):
            return {"X.US": df}

    text = fetch_market_data_json(
        codes=["X.US"],
        start_date="2026-01-01",
        end_date="2026-01-02",
        source="yfinance",
        loader_resolver=lambda source: _Loader,
    )

    assert "NaN" not in text
    payload = json.loads(text)
    assert payload["X.US"][0]["high"] is None


def test_swarm_registry_can_expose_local_get_market_data_tool():
    registry = build_swarm_registry(["get_market_data"])

    assert "get_market_data" in registry.tool_names


def test_every_market_data_worker_has_get_market_data_tool():
    """Workers with OHLCV-capable skills must expose the loader-backed tool (#198)."""
    market_data_skills = {"tushare", "yfinance", "okx-market"}
    missing = []
    for summary in list_presets():
        preset = load_preset(summary["name"])
        for agent in preset.get("agents", []):
            if market_data_skills & set(agent.get("skills", [])):
                if "get_market_data" not in (agent.get("tools") or []):
                    missing.append(f"{summary['name']}:{agent['id']}")

    assert not missing, f"workers with market-data skills lack get_market_data: {missing}"


def test_worker_prompt_prioritizes_get_market_data_for_ohlcv():
    spec = SwarmAgentSpec(
        id="analyst",
        role="Analyst",
        system_prompt="Analyze prices.",
        tools=["load_skill", "get_market_data", "write_file"],
        skills=["yfinance"],
    )

    prompt = build_worker_prompt(spec, {}, "  - yfinance: market data")

    assert "Market Data Tool Policy" in prompt
    assert "call `get_market_data` before writing raw provider scripts" in prompt


def test_system_prompt_marks_todays_korean_daily_bar_as_provisional():
    assert "`as_of` or `latest_ohlcv.date` is today" in _SYSTEM_PROMPT
    assert "cumulative intraday volume" in _SYSTEM_PROMPT
    assert "never as a confirmed close/final volume" in _SYSTEM_PROMPT
    assert (
        "오늘 데이터는 장중 미완성 일봉일 수 있으며, "
        "현재가·고가·저가·거래량은 장 마감 후 달라질 수 있습니다."
    ) in _SYSTEM_PROMPT


class _FakeRemote:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payload(kwargs) if callable(self.payload) else self.payload
        return json.dumps(payload)


def _ohlcv_payload(rows=220):
    data = []
    for i, date in enumerate(pd.date_range("2025-01-01", periods=rows, freq="B"), start=1):
        data.append({
            "날짜": date.strftime("%Y-%m-%d"), "시가": i, "고가": i + 2,
            "저가": i - 1, "종가": i + 1, "거래량": i * 100,
        })
    return {"status": "ok", "data": {"ticker": "005930", "row_count": rows, "data": data}}


def _error(message):
    return {"status": "ok", "data": {"error": message}}


def test_korean_symbol_detection_is_explicit_and_bare_requires_hint():
    for symbol in ("005930.KS", "035720.KQ", "KRX:005930", "KOSPI:005930", "KOSDAQ:035720"):
        assert is_korean_equity(symbol)
    assert is_korean_equity("005930", market="kr")
    assert not is_korean_equity("005930", market="auto")
    assert not is_korean_equity("000001.SZ", market="kr")


def test_bare_korean_uses_pykrx_first_and_never_calls_price_loader():
    ohlcv = _FakeRemote(_ohlcv_payload())
    loader_calls = []
    result = fetch_market_data(
        codes=["005930"], start_date="2025-10-01", end_date="2025-12-31", market="kr",
        fields=["ohlcv", "derived"], mcp_tools={"get_stock_ohlcv": ohlcv},
        loader_resolver=lambda source: loader_calls.append(source), max_rows=0,
    )
    assert len(ohlcv.calls) == 1
    assert loader_calls == []
    assert result["005930"]["provenance"]["ohlcv"] == {
        "source": "pykrx_mcp", "fallback": False, "status": "ok"
    }


def test_explicit_korean_symbol_uses_pykrx_without_market_hint():
    ohlcv = _FakeRemote(_ohlcv_payload())
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        fields=["ohlcv"], mcp_tools={"get_stock_ohlcv": ohlcv}, max_rows=0,
    )
    assert result["005930.KS"]["ticker"] == "005930"
    assert len(ohlcv.calls) == 1


def test_group_failures_are_isolated_and_fallback_cannot_overwrite_ohlcv():
    tools = {
        "get_stock_ohlcv": _FakeRemote(_ohlcv_payload()),
        "get_market_fundamental_by_date": _FakeRemote(_error("fundamental empty")),
        "get_market_cap_by_date": _FakeRemote(_error("market cap empty")),
        "get_market_trading_value_by_investor": _FakeRemote(_error("investor empty")),
    }
    fallback_calls = []

    def fallback(**kwargs):
        fallback_calls.append(kwargs)
        return {"PER": 10, "close": -1, "volume": -1}

    fallback.source = "test_fallback"
    result = fetch_market_data(
        codes=["005930"], start_date="2025-01-01", end_date="2025-12-31", market="kr",
        mcp_tools=tools, fallback_resolvers={"fundamentals": fallback}, max_rows=0,
    )["005930"]
    assert len(fallback_calls) == 1
    assert result["fundamentals"]["close"] == -1
    assert result["ohlcv"][-1]["close"] == 221.0
    assert result["ohlcv"][-1]["volume"] == 22000.0
    assert result["provenance"]["fundamentals"]["fallback"] is True
    assert "fundamental empty" in result["provenance"]["fundamentals"]["primary_failure"]
    for group in ("market_cap", "investor_flow"):
        assert result[group] is None
        assert result["provenance"][group]["status"] == "unavailable"
        assert result["provenance"][group]["primary_failure"]
    assert result["provenance"]["ohlcv"]["source"] == "pykrx_mcp"


def test_derived_indicators_use_pykrx_close_and_volume():
    result = fetch_market_data(
        codes=["005930"], start_date="2025-01-01", end_date="2025-12-31", market="kr",
        fields=["ohlcv", "derived"], mcp_tools={"get_stock_ohlcv": _FakeRemote(_ohlcv_payload())},
        max_rows=0,
    )["005930"]
    close = pd.Series(range(2, 222), dtype=float)
    for window in (20, 60, 120, 200):
        name = f"ma{window}"
        assert result["derived"][name] == close.tail(window).mean()
        assert result["provenance"]["derived"][name]["upstream_source"] == "pykrx_mcp"
    assert result["derived"]["volume_average"] == pd.Series(range(100, 22001, 100)).mean()
    assert result["provenance"]["derived"]["volume_average"]["computed_from"] == "ohlcv.volume"


def test_period_return_uses_requested_range_while_ma200_uses_warmup_rows():
    dates = pd.bdate_range("2025-01-02", "2026-08-12")
    rows = [
        {
            "date": date.strftime("%Y-%m-%d"), "open": i, "high": i + 2,
            "low": i - 1, "close": i + 1, "volume": i * 100,
        }
        for i, date in enumerate(dates, start=1)
    ]
    payload = {"status": "ok", "data": {"data": rows}}
    result = fetch_market_data(
        codes=["005930"], start_date="2026-01-02", end_date="2026-08-12",
        market="kr", fields=["ohlcv", "derived"],
        mcp_tools={"get_stock_ohlcv": _FakeRemote(payload)}, max_rows=0,
    )["005930"]

    closes = pd.Series(
        [row["close"] for row in rows], index=pd.DatetimeIndex(dates), dtype=float,
    )
    requested = closes.loc["2026-01-02":"2026-08-12"]
    assert result["derived"]["ma200"] == closes.tail(200).mean()
    assert result["derived"]["period_return"] == requested.iloc[-1] / requested.iloc[0] - 1
    assert result["derived"]["period_return"] != closes.iloc[-1] / closes.iloc[0] - 1


def test_period_return_starts_on_first_trading_day_after_weekend():
    rows = [
        {"date": "2025-12-31", "open": 49, "high": 51, "low": 48, "close": 50, "volume": 10},
        {"date": "2026-01-05", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 20},
        {"date": "2026-01-06", "open": 109, "high": 111, "low": 108, "close": 110, "volume": 30},
    ]
    result = fetch_market_data(
        codes=["005930"], start_date="2026-01-03", end_date="2026-01-06",
        market="kr", fields=["ohlcv", "derived"],
        mcp_tools={"get_stock_ohlcv": _FakeRemote({"status": "ok", "data": {"data": rows}})},
        max_rows=0,
    )["005930"]

    assert result["derived"]["period_return"] == 110 / 100 - 1


def test_korean_summary_precedes_full_ohlcv_and_survives_tool_truncation():
    rows = []
    dates = pd.bdate_range(end="2026-08-12", periods=420)
    for i, date in enumerate(dates, start=1):
        rows.append({
            "date": date.strftime("%Y-%m-%d"), "open": i, "high": i + 2,
            "low": i - 1, "close": i + 1, "volume": i * 100,
        })
    payload = {
        "status": "ok",
        "data": {"ticker": "005930", "row_count": len(rows), "data": rows},
    }
    result = fetch_market_data(
        codes=["005930"], start_date="2025-08-12", end_date="2026-08-12",
        market="kr", fields=["ohlcv", "derived"],
        mcp_tools={"get_stock_ohlcv": _FakeRemote(payload)}, max_rows=0,
    )["005930"]

    assert result["as_of"] == "2026-08-12"
    assert result["latest_ohlcv"]["date"] == "2026-08-12"
    for field in ("open", "high", "low", "close", "volume"):
        assert result["latest_ohlcv"][field] == result["ohlcv"][-1][field]
    # MA200 must use all normalized bars, not a reduced LLM-facing series.
    expected_ma200 = pd.Series(range(222, 422), dtype=float).mean()
    assert result["derived"]["ma200"] == expected_ma200

    serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
    full_ohlcv_position = serialized.index('"ohlcv": [')
    for key in ('"as_of"', '"latest_ohlcv"', '"derived"', '"provenance"'):
        assert serialized.index(key) < full_ohlcv_position
    clipped = serialized[:10_000]
    assert "2026-08-12" in clipped
    assert '"ma200"' in clipped
    assert '"upstream_source": "pykrx_mcp"' in clipped
    assert '"source": "pykrx_mcp"' in clipped


def test_non_korean_market_keeps_existing_loader_route():
    calls = []
    idx = pd.date_range("2026-01-01", periods=1)

    class _Loader:
        def fetch(self, codes, start, end, interval="1D"):
            calls.append(codes)
            return {codes[0]: pd.DataFrame({
                "open": [1], "high": [2], "low": [0], "close": [1], "volume": [3]
            }, index=idx)}

    result = fetch_market_data(
        codes=["000001.SZ"], start_date="2026-01-01", end_date="2026-01-02",
        loader_resolver=lambda source: _Loader,
    )
    assert calls == [["000001.SZ"]]
    assert "000001.SZ" in result
