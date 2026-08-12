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


class _InfoResolver:
    def __init__(self, info=None, error=None):
        self.info = info or {}
        self.error = error
        self.calls = []

    def __call__(self, symbol):
        self.calls.append(symbol)
        if self.error:
            raise self.error
        return self.info


def _fundamentals_payload(**values):
    return {"status": "ok", "data": {"data": [{"날짜": "2025-12-31", **values}]}}


def _market_cap_payload(value):
    return {"status": "ok", "data": {"data": [{"날짜": "2025-12-31", "시가총액": value}]}}


def test_pykrx_non_price_fields_succeed_without_yfinance():
    info = _InfoResolver(error=AssertionError("yfinance must not be called"))
    tools = {
        "get_stock_ohlcv": _FakeRemote(_ohlcv_payload()),
        "get_market_fundamental_by_date": _FakeRemote(
            _fundamentals_payload(PER=10, PBR=1.5, EPS=5000, BPS=50000)
        ),
        "get_market_cap_by_date": _FakeRemote(_market_cap_payload(123_000_000)),
    }
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        fields=["ohlcv", "fundamentals", "market_cap"], mcp_tools=tools,
        yfinance_info_resolver=info, max_rows=0,
    )["005930.KS"]

    assert info.calls == []
    assert result["fundamentals"] == {"PER": 10, "PBR": 1.5, "EPS": 5000, "BPS": 50000}
    assert result["market_cap"] == 123_000_000
    assert all(
        item["source"] == "pykrx_mcp"
        for item in result["provenance"]["fundamentals"]["fields"].values()
    )
    assert result["provenance"]["market_cap"]["source"] == "pykrx_mcp"


def test_fundamental_fallback_fills_only_missing_fields_and_records_provenance():
    info = _InfoResolver({
        "trailingPE": 12, "priceToBook": 2.0, "trailingEps": 6000, "bookValue": 70000,
    })
    tools = {
        "get_stock_ohlcv": _FakeRemote(_ohlcv_payload()),
        "get_market_fundamental_by_date": _FakeRemote(
            _fundamentals_payload(PER=None, PBR=1.5, EPS=None, BPS=50000)
        ),
    }
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        fields=["ohlcv", "fundamentals"], mcp_tools=tools,
        yfinance_info_resolver=info, max_rows=0,
    )["005930.KS"]

    assert info.calls == ["005930.KS"]
    assert result["fundamentals"] == {"PER": 12, "PBR": 1.5, "EPS": 6000, "BPS": 50000}
    fields = result["provenance"]["fundamentals"]["fields"]
    assert fields["PBR"] == {"source": "pykrx_mcp", "fallback": False, "status": "ok"}
    assert fields["BPS"]["source"] == "pykrx_mcp"
    assert fields["PER"]["provider_field"] == "trailingPE"
    assert fields["PER"]["basis"] == "trailing"
    assert fields["EPS"]["provider_field"] == "trailingEps"
    for field in ("PER", "EPS"):
        assert fields[field]["source"] == "yfinance"
        assert fields[field]["as_of_type"] == "current_snapshot"
        assert fields[field]["fallback"] is True
        assert fields[field]["status"] == "ok"
        assert fields[field]["primary_failure"]


def test_invalid_yfinance_values_remain_unavailable():
    info = _InfoResolver({
        "trailingPE": None, "priceToBook": float("nan"),
        "trailingEps": float("inf"), "bookValue": float("-inf"),
    })
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        fields=["fundamentals"],
        mcp_tools={"get_market_fundamental_by_date": _FakeRemote(_error("fundamental empty"))},
        yfinance_info_resolver=info,
    )["005930.KS"]

    assert result["fundamentals"] == {"PER": None, "PBR": None, "EPS": None, "BPS": None}
    for item in result["provenance"]["fundamentals"]["fields"].values():
        assert item["source"] == "unavailable"
        assert item["status"] == "unavailable"
        assert "fundamental empty" in item["primary_failure"]


def test_bare_korean_ticker_does_not_guess_yfinance_board():
    info = _InfoResolver(error=AssertionError("ambiguous bare ticker must not call yfinance"))
    result = fetch_market_data(
        codes=["005930"], start_date="2025-01-01", end_date="2025-12-31", market="kr",
        fields=["fundamentals", "market_cap"],
        mcp_tools={
            "get_market_fundamental_by_date": _FakeRemote(_error("fundamental empty")),
            "get_market_cap_by_date": _FakeRemote(_error("market cap empty")),
        },
        yfinance_info_resolver=info,
    )["005930"]

    assert info.calls == []
    assert result["market_cap"] is None
    assert all(value is None for value in result["fundamentals"].values())
    assert "board is not explicit" in result["provenance"]["market_cap"]["primary_failure"]


def test_group_failures_are_isolated_and_yfinance_price_fields_are_ignored():
    tools = {
        "get_stock_ohlcv": _FakeRemote(_ohlcv_payload()),
        "get_market_fundamental_by_date": _FakeRemote(_error("fundamental empty")),
        "get_market_cap_by_date": _FakeRemote(_error("market cap empty")),
        "get_market_trading_volume_by_investor": _FakeRemote(_error("investor volume empty")),
        "get_market_trading_value_by_investor": _FakeRemote(_error("investor empty")),
    }
    info = _InfoResolver({
        "trailingPE": 12, "priceToBook": 2, "trailingEps": 5000,
        "bookValue": 60000, "marketCap": 999_000_000,
        "currentPrice": 999999999, "open": 888888888, "volume": 777777777,
    })
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        mcp_tools=tools, yfinance_info_resolver=info, max_rows=0,
    )["005930.KS"]
    assert info.calls == ["005930.KS"]
    assert result["fundamentals"] == {"PER": 12, "PBR": 2, "EPS": 5000, "BPS": 60000}
    assert result["market_cap"] == 999_000_000
    assert result["ohlcv"][-1]["close"] == 221.0
    assert result["ohlcv"][-1]["volume"] == 22000.0
    assert result["latest_ohlcv"]["close"] == 221.0
    assert result["latest_ohlcv"]["volume"] == 22000.0
    assert result["derived"]["ma20"] == pd.Series(range(202, 222), dtype=float).mean()
    assert result["provenance"]["fundamentals"]["fallback"] is True
    assert result["provenance"]["market_cap"] == {
        "source": "yfinance", "provider_field": "marketCap",
        "as_of_type": "current_snapshot", "fallback": True, "status": "ok",
        "primary_failure": "market cap empty",
    }
    assert result["investor_flow"] == {"volume": None, "value": None}
    assert result["provenance"]["investor_flow"]["status"] == "unavailable"
    assert result["provenance"]["investor_flow"]["fallback"] is False
    assert result["provenance"]["ohlcv"]["source"] == "pykrx_mcp"


def test_investor_flow_never_calls_yfinance_and_preserves_partial_pykrx_success():
    info = _InfoResolver(error=AssertionError("investor flow must not call yfinance"))
    tools = {
        "get_stock_ohlcv": _FakeRemote(_ohlcv_payload()),
        "get_market_trading_volume_by_investor": _FakeRemote(
            {"status": "ok", "data": {"data": {"외국인": {"순매수": 10}}}}
        ),
        "get_market_trading_value_by_investor": _FakeRemote(_error("value unavailable")),
    }
    result = fetch_market_data(
        codes=["005930.KS"], start_date="2025-01-01", end_date="2025-12-31",
        fields=["ohlcv", "investor_flow"], mcp_tools=tools,
        yfinance_info_resolver=info,
    )["005930.KS"]

    assert info.calls == []
    assert result["investor_flow"]["volume"] == {"외국인": {"순매수": 10}}
    assert result["investor_flow"]["value"] is None
    parts = result["provenance"]["investor_flow"]["parts"]
    assert parts["volume"]["status"] == "ok"
    assert parts["value"]["status"] == "unavailable"


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


def test_extended_derived_values_use_pykrx_ohlcv_and_calendar_anchors():
    dates = pd.bdate_range("2025-12-01", "2026-08-12")
    rows = [
        {
            "date": date.strftime("%Y-%m-%d"), "open": i, "high": i + 2,
            "low": i - 1, "close": 100 + i, "volume": 1_000 + i * 10,
        }
        for i, date in enumerate(dates)
    ]
    result = fetch_market_data(
        codes=["005930"], start_date="2026-01-05", end_date="2026-08-12",
        market="kr", fields=["ohlcv", "derived"],
        mcp_tools={
            "get_stock_ohlcv": _FakeRemote({"status": "ok", "data": {"data": rows}})
        },
        max_rows=0,
    )["005930"]

    frame = pd.DataFrame(rows).assign(date=lambda item: pd.to_datetime(item["date"])).set_index("date")
    requested = frame.loc["2026-01-05":"2026-08-12"]
    latest_close = frame["close"].iloc[-1]
    anchors = {
        "return_1w": frame.index[-1] - pd.Timedelta(days=7),
        "return_1m": frame.index[-1] - pd.DateOffset(months=1),
        "return_3m": frame.index[-1] - pd.DateOffset(months=3),
        "return_6m": frame.index[-1] - pd.DateOffset(months=6),
    }
    for name, anchor in anchors.items():
        anchor_close = frame.loc[frame.index <= anchor, "close"].iloc[-1]
        assert result["derived"][name] == latest_close / anchor_close - 1

    # 2026-07-12 was a Sunday, so the one-month anchor uses Friday 2026-07-10.
    assert frame.loc[frame.index <= pd.Timestamp("2026-07-12")].index[-1] == pd.Timestamp("2026-07-10")
    assert result["derived"]["period_return"] == (
        requested["close"].iloc[-1] / requested["close"].iloc[0] - 1
    )
    for window in (20, 60, 120):
        name = f"volume_average_{window}d"
        assert result["derived"][name] == frame["volume"].tail(window).mean()
    assert result["derived"]["period_volume_average"] == requested["volume"].mean()
    assert result["derived"]["volume_average"] == result["derived"]["period_volume_average"]
    expected_volatility = requested["close"].pct_change().dropna().std(ddof=1) * (252 ** 0.5)
    assert result["derived"]["volatility_annualized"] == expected_volatility

    new_fields = set(anchors) | {
        "volume_average_20d", "volume_average_60d", "volume_average_120d",
        "period_volume_average", "volatility_annualized",
    }
    for name in new_fields:
        assert result["provenance"]["derived"][name]["upstream_source"] == "pykrx_mcp"
    volatility_provenance = result["provenance"]["derived"]["volatility_annualized"]
    assert volatility_provenance["computed_from"] == "ohlcv.close.pct_change"
    assert volatility_provenance["annualization_factor"] == 252
    assert volatility_provenance["estimator"] == "sample_std"


def test_extended_derived_returns_none_when_anchor_or_sample_is_insufficient():
    rows = [
        {
            "date": date.strftime("%Y-%m-%d"), "open": i, "high": i + 2,
            "low": i - 1, "close": 100 + i, "volume": 1_000 + i,
        }
        for i, date in enumerate(pd.bdate_range("2026-08-06", "2026-08-12"))
    ]
    result = fetch_market_data(
        codes=["005930"], start_date="2026-08-12", end_date="2026-08-12",
        market="kr", fields=["ohlcv", "derived"],
        mcp_tools={
            "get_stock_ohlcv": _FakeRemote({"status": "ok", "data": {"data": rows}})
        },
        max_rows=0,
    )["005930"]["derived"]

    for name in ("return_1w", "return_1m", "return_3m", "return_6m"):
        assert result[name] is None
    for name in ("volume_average_20d", "volume_average_60d", "volume_average_120d"):
        assert result[name] is None
    assert result["period_return"] is None
    assert result["volatility_annualized"] is None


def test_korean_market_data_prompts_enforce_reuse_factuality_and_score_separation():
    from src.tools.market_data_tool import MarketDataTool

    assert "same symbol and requested range or any subrange" in _SYSTEM_PROMPT
    assert "same symbol and requested range or any subrange" in MarketDataTool.description
    assert "추가 기업/뉴스 데이터 필요" in _SYSTEM_PROMPT
    assert "exclude that item from scoring" in _SYSTEM_PROMPT
    assert "PER/PBR/EPS/BPS alone do not establish financial stability" in _SYSTEM_PROMPT
    assert "시장데이터 기반 기술·밸류에이션 점수" in _SYSTEM_PROMPT
    assert "완전한 장기투자 점수: 산정 보류" in _SYSTEM_PROMPT


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
