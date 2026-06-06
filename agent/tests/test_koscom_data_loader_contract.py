"""Koscom CHECK/OpenAPI market data loader contracts."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from backtest.loaders.koscom import DataLoader, _normalize_koscom_symbol
from backtest.loaders.registry import FALLBACK_CHAINS, LOADER_REGISTRY, resolve_loader


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_koscom_loader_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KOSCOM_OPEN_API_KEY", raising=False)
    monkeypatch.delenv("KOSCOM_CHECK_API_KEY", raising=False)
    monkeypatch.delenv("VIBE_TRADING_KOSCOM_API_KEY", raising=False)

    loader = DataLoader()

    assert loader.requires_auth is True
    assert loader.is_available() is False


def test_koscom_loader_registered_after_krx_before_public_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")
    with patch.dict(LOADER_REGISTRY, {"koscom": DataLoader}, clear=True):
        with patch.dict(FALLBACK_CHAINS, {"kr_equity": ["koscom"]}):
            assert resolve_loader("kr_equity").name == "koscom"


def test_koscom_symbol_normalization_keeps_market_board() -> None:
    assert _normalize_koscom_symbol("005930.KS") == ("kospi", "005930")
    assert _normalize_koscom_symbol("KOSPI:5930") == ("kospi", "005930")
    assert _normalize_koscom_symbol("035720.KQ") == ("kosdaq", "035720")
    assert _normalize_koscom_symbol("KOSDAQ:35720") == ("kosdaq", "035720")
    assert _normalize_koscom_symbol("KRX:005930") == ("kospi", "005930")


def test_koscom_loader_gets_apikey_query_and_normalizes_history_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_get(url: str, *, params: dict, timeout: float) -> _Resp:
        calls.append({"url": url, "params": params, "timeout": timeout})
        return _Resp(
            {
                "data": [
                    {
                        "trdDd": "20260102",
                        "isuSrtCd": "005930",
                        "opnPrc": "70,000",
                        "hgPrc": "71,000",
                        "lwPrc": "69,000",
                        "clPrc": "70,500",
                        "accTrdVol": "123,456",
                    },
                    {
                        "trdDd": "20260105",
                        "isuSrtCd": "000660",
                        "opnPrc": "100000",
                        "hgPrc": "101000",
                        "lwPrc": "99000",
                        "clPrc": "100500",
                        "accTrdVol": "999",
                    },
                ]
            }
        )

    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")
    monkeypatch.setattr("backtest.loaders.koscom.requests.get", fake_get)

    result = DataLoader().fetch(["005930.KS"], "2026-01-02", "2026-01-05")

    assert calls == [
        {
            "url": "https://oap.k-mydata.org/v3/market/closed/kospi/005930/history",
            "params": {"apikey": "test-key"},
            "timeout": 20,
        }
    ]
    frame = result["005930.KS"]
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert list(frame.index) == [pd.Timestamp("2026-01-02")]
    assert frame.loc[pd.Timestamp("2026-01-02"), "close"] == 70500.0


def test_koscom_loader_uses_kosdaq_history_endpoint_for_kq_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_get(url: str, *, params: dict, timeout: float) -> _Resp:
        calls.append({"url": url, "params": params, "timeout": timeout})
        return _Resp(
            {
                "result": {
                    "list": [
                        {
                            "date": "2026-01-02",
                            "issuecode": "035720",
                            "open": "50000",
                            "high": "51000",
                            "low": "49000",
                            "close": "50500",
                            "volume": "1234",
                        },
                    ]
                }
            }
        )

    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")
    monkeypatch.setattr("backtest.loaders.koscom.requests.get", fake_get)

    result = DataLoader().fetch(["035720.KQ"], "2026-01-02", "2026-01-02")

    assert result["035720.KQ"].loc[pd.Timestamp("2026-01-02"), "close"] == 50500.0
    assert calls[0]["url"].endswith("/v3/market/closed/kosdaq/035720/history")


def test_koscom_loader_rejects_intraday_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")

    with pytest.raises(ValueError, match="daily"):
        DataLoader().fetch(["005930.KS"], "2026-01-02", "2026-01-05", interval="1H")


def test_koscom_loader_fetches_country_holidays_with_apikey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_get(url: str, *, params: dict, timeout: float) -> _Resp:
        calls.append({"url": url, "params": params, "timeout": timeout})
        return _Resp(
            {
                "data": [
                    {"date": "20260101", "name": "New Year"},
                    {"holidayDate": "2026-02-17", "holidayName": "Lunar New Year"},
                    {"trdDd": "2026-05-05", "calndDd": "2026-05-05"},
                ]
            }
        )

    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")
    monkeypatch.setattr("backtest.loaders.koscom.requests.get", fake_get)

    holidays = DataLoader().fetch_holidays()

    assert calls == [
        {
            "url": "https://oap.k-mydata.org/v3/market/extra/stocks/KR/holiday",
            "params": {"apikey": "test-key"},
            "timeout": 20,
        }
    ]
    assert holidays == {
        pd.Timestamp("2026-01-01").date(),
        pd.Timestamp("2026-02-17").date(),
        pd.Timestamp("2026-05-05").date(),
    }
