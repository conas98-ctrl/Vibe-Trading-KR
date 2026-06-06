"""Korean equity data/backtest routing contracts."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

import backtest.loaders.yfinance_loader as yfinance_loader
from backtest.benchmark import _infer_market, _resolve_ticker
from backtest.engines.global_equity import GlobalEquityEngine
from backtest.engines.kr_market import KoreanTradingCalendar, KoscomHolidayProvider
from backtest.loaders.registry import FALLBACK_CHAINS, LOADER_REGISTRY, resolve_loader
from backtest.loaders.yfinance_loader import DataLoader, _to_yfinance_symbol
from backtest.runner import _create_market_engine


def test_yfinance_loader_declares_korean_equity_support(monkeypatch) -> None:
    assert "kr_equity" in DataLoader.markets
    monkeypatch.setattr(yfinance_loader, "yf", object())
    with patch.dict(LOADER_REGISTRY, {"yfinance": DataLoader}, clear=True):
        with patch.dict(FALLBACK_CHAINS, {"kr_equity": ["yfinance"]}):
            assert resolve_loader("kr_equity").name == "yfinance"


def test_korean_symbols_convert_to_yfinance_contracts() -> None:
    assert _to_yfinance_symbol("005930.KS") == "005930.KS"
    assert _to_yfinance_symbol("035720.KQ") == "035720.KQ"
    assert _to_yfinance_symbol("KRX:005930") == "005930.KS"
    assert _to_yfinance_symbol("KR.005930") == "005930.KS"
    assert _to_yfinance_symbol("KOSPI:005930") == "005930.KS"
    assert _to_yfinance_symbol("KOSDAQ:035720") == "035720.KQ"


def test_korean_equity_backtest_uses_kr_global_equity_rules() -> None:
    engine = _create_market_engine(
        "yfinance",
        {"initial_cash": 1_000_000},
        ["005930.KS", "035720.KQ"],
    )

    assert isinstance(engine, GlobalEquityEngine)
    assert engine.market == "kr"


def test_korean_global_equity_rules_are_long_only_and_one_share_lot() -> None:
    engine = GlobalEquityEngine({"initial_cash": 1_000_000}, market="kr")
    bar = pd.Series({"close": 70_000, "pre_close": 69_000})

    assert engine.round_size(10.7, 70_000) == 10
    assert engine.can_execute("005930.KS", -1, bar) is False
    assert engine.can_execute("005930.KS", 1, bar) is True


def test_korean_price_limit_blocks_buy_and_sell_at_krx_limit() -> None:
    engine = GlobalEquityEngine({"initial_cash": 1_000_000}, market="kr")

    assert engine.can_execute(
        "005930.KS",
        1,
        pd.Series({"close": 130_000, "pre_close": 100_000}),
    ) is False
    assert engine.can_execute(
        "005930.KS",
        0,
        pd.Series({"close": 70_000, "pre_close": 100_000}),
    ) is False


def test_korean_sell_proceeds_settle_t2_before_reuse() -> None:
    engine = GlobalEquityEngine(
        {
            "initial_cash": 100_000,
            "slippage_kr": 0.0,
            "kr_commission": 0.0,
            "kr_transaction_tax": 0.0,
        },
        market="kr",
    )
    dates = pd.DatetimeIndex(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [10_000, 10_000, 10_000, 10_000],
            "close": [10_000, 10_000, 10_000, 10_000],
            "pre_close": [10_000, 10_000, 10_000, 10_000],
        },
        index=dates,
    )
    close_df = pd.DataFrame({"005930.KS": [10_000, 10_000, 10_000, 10_000]}, index=dates)
    target_pos = pd.DataFrame({"005930.KS": [1.0, 0.0, 1.0, 1.0]}, index=dates)

    engine._execute_bars(dates, {"005930.KS": frame}, close_df, target_pos, ["005930.KS"])

    snapshots = {snapshot.timestamp: snapshot for snapshot in engine.equity_snapshots}
    assert snapshots[dates[1]].positions == 0
    assert snapshots[dates[1]].capital == 0
    assert snapshots[dates[1]].equity == 100_000
    assert snapshots[dates[2]].positions == 0
    assert snapshots[dates[2]].capital == 0
    assert snapshots[dates[2]].equity == 100_000
    assert snapshots[dates[3]].positions == 1


def test_korean_settlement_uses_trading_calendar_holidays() -> None:
    engine = GlobalEquityEngine(
        {
            "initial_cash": 100_000,
            "slippage_kr": 0.0,
            "kr_commission": 0.0,
            "kr_transaction_tax": 0.0,
            "kr_holidays": ["2026-01-06"],
        },
        market="kr",
    )
    dates = pd.DatetimeIndex(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [10_000, 10_000, 10_000, 10_000, 10_000],
            "close": [10_000, 10_000, 10_000, 10_000, 10_000],
            "pre_close": [10_000, 10_000, 10_000, 10_000, 10_000],
        },
        index=dates,
    )
    close_df = pd.DataFrame(
        {"005930.KS": [10_000, 10_000, 10_000, 10_000, 10_000]},
        index=dates,
    )
    target_pos = pd.DataFrame({"005930.KS": [1.0, 0.0, 1.0, 1.0, 1.0]}, index=dates)

    engine._execute_bars(dates, {"005930.KS": frame}, close_df, target_pos, ["005930.KS"])

    snapshots = {snapshot.timestamp: snapshot for snapshot in engine.equity_snapshots}
    assert snapshots[dates[1]].positions == 0
    assert snapshots[dates[1]].capital == 0
    assert snapshots[dates[2]].positions == 0
    assert snapshots[dates[3]].positions == 0
    assert snapshots[dates[3]].capital == 0
    assert snapshots[dates[4]].positions == 1


def test_korean_settlement_can_use_live_holiday_provider_contract() -> None:
    class _Provider:
        def fetch_holidays(self, *, nation_code: str = "KR"):
            assert nation_code == "KR"
            return {pd.Timestamp("2026-01-06").date()}

    engine = GlobalEquityEngine(
        {
            "initial_cash": 100_000,
            "slippage_kr": 0.0,
            "kr_commission": 0.0,
            "kr_transaction_tax": 0.0,
            "kr_holiday_provider": _Provider(),
        },
        market="kr",
    )
    dates = pd.DatetimeIndex(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
        ]
    )
    frame = pd.DataFrame(
        {
            "open": [10_000, 10_000, 10_000, 10_000, 10_000],
            "close": [10_000, 10_000, 10_000, 10_000, 10_000],
            "pre_close": [10_000, 10_000, 10_000, 10_000, 10_000],
        },
        index=dates,
    )
    close_df = pd.DataFrame(
        {"005930.KS": [10_000, 10_000, 10_000, 10_000, 10_000]},
        index=dates,
    )
    target_pos = pd.DataFrame({"005930.KS": [1.0, 0.0, 1.0, 1.0, 1.0]}, index=dates)

    engine._execute_bars(dates, {"005930.KS": frame}, close_df, target_pos, ["005930.KS"])

    snapshots = {snapshot.timestamp: snapshot for snapshot in engine.equity_snapshots}
    assert snapshots[dates[2]].positions == 0
    assert snapshots[dates[3]].positions == 0
    assert snapshots[dates[4]].positions == 1


def test_korean_calendar_observes_weekends_holidays_and_year_end_closure() -> None:
    calendar = KoreanTradingCalendar(holidays=["2026-01-01"])

    assert calendar.is_trading_day("2026-01-02") is True
    assert calendar.is_trading_day("2026-01-03") is False
    assert calendar.is_trading_day("2026-01-01") is False
    assert calendar.is_trading_day("2026-12-31") is False


def test_korean_calendar_can_load_koscom_holiday_provider() -> None:
    class _Provider:
        def fetch_holidays(self, *, nation_code: str = "KR"):
            assert nation_code == "KR"
            return {pd.Timestamp("2026-01-06").date()}

    calendar = KoreanTradingCalendar.from_holiday_provider(_Provider())

    assert calendar.is_trading_day("2026-01-06") is False


def test_koscom_holiday_provider_delegates_to_loader() -> None:
    class _Loader:
        def fetch_holidays(self, *, nation_code: str = "KR"):
            assert nation_code == "KR"
            return {pd.Timestamp("2026-01-06").date()}

    provider = KoscomHolidayProvider(loader=_Loader())

    assert provider.fetch_holidays() == {pd.Timestamp("2026-01-06").date()}


def test_korean_market_sessions_separate_krx_and_nxt_hours() -> None:
    calendar = KoreanTradingCalendar(holidays=["2026-01-06"])

    assert calendar.session_for("2026-01-05 09:10", venue="krx") == "regular"
    assert calendar.session_for("2026-01-05 19:00", venue="krx") is None
    assert calendar.session_for("2026-01-05 08:10", venue="nxt") == "pre_market"
    assert calendar.session_for("2026-01-05 19:00", venue="nxt") == "after_market"
    assert calendar.session_for("2026-01-06 09:10", venue="nxt") is None


def test_korean_benchmark_resolves_to_kospi_index_for_yfinance() -> None:
    assert _infer_market(["005930.KS"], "yfinance") == "kr_equity"
    assert _infer_market(["KRX:005930"], "yfinance") == "kr_equity"
    assert _resolve_ticker(["005930.KS"], "yfinance", explicit=None) == "^KS11"
