"""KRX Data Marketplace loader contracts."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from backtest.loaders.krx import DataLoader, _normalize_krx_symbol
from backtest.loaders.registry import FALLBACK_CHAINS, LOADER_REGISTRY, resolve_loader


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_krx_loader_requires_auth_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRX_OPEN_API_AUTH_KEY", raising=False)
    monkeypatch.delenv("VIBE_TRADING_KRX_AUTH_KEY", raising=False)

    loader = DataLoader()

    assert loader.requires_auth is True
    assert loader.is_available() is False


def test_krx_loader_registered_for_korean_market(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRX_OPEN_API_AUTH_KEY", "test-key")
    with patch.dict(LOADER_REGISTRY, {"krx": DataLoader}, clear=True):
        with patch.dict(FALLBACK_CHAINS, {"kr_equity": ["krx"]}):
            assert resolve_loader("kr_equity").name == "krx"


def test_krx_symbol_normalization_keeps_market_board() -> None:
    assert _normalize_krx_symbol("005930.KS") == ("kospi", "005930")
    assert _normalize_krx_symbol("KOSPI:5930") == ("kospi", "005930")
    assert _normalize_krx_symbol("035720.KQ") == ("kosdaq", "035720")
    assert _normalize_krx_symbol("KOSDAQ:35720") == ("kosdaq", "035720")
    assert _normalize_krx_symbol("KRX:005930") == ("kospi", "005930")


def test_krx_loader_builds_auth_header_and_normalizes_daily_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_get(url: str, *, params: dict, headers: dict, timeout: float) -> _Resp:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return _Resp(
            {
                "OutBlock_1": [
                    {
                        "BAS_DD": "20260102",
                        "ISU_CD": "005930",
                        "TDD_OPNPRC": "70000",
                        "TDD_HGPRC": "71000",
                        "TDD_LWPRC": "69000",
                        "TDD_CLSPRC": "70500",
                        "ACC_TRDVOL": "123456",
                    },
                    {
                        "BAS_DD": "20260105",
                        "ISU_CD": "000660",
                        "TDD_OPNPRC": "100000",
                        "TDD_HGPRC": "101000",
                        "TDD_LWPRC": "99000",
                        "TDD_CLSPRC": "100500",
                        "ACC_TRDVOL": "999",
                    },
                ]
            }
        )

    monkeypatch.setenv("KRX_OPEN_API_AUTH_KEY", "test-key")
    monkeypatch.setattr("backtest.loaders.krx.requests.get", fake_get)

    result = DataLoader().fetch(["005930.KS"], "2026-01-02", "2026-01-05")

    assert calls
    assert calls[0]["headers"] == {"AUTH_KEY": "test-key"}
    assert calls[0]["params"] == {"basDd": "20260102"}
    assert calls[0]["url"].endswith("/svc/apis/sto/stk_bydd_trd")
    frame = result["005930.KS"]
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert list(frame.index) == [pd.Timestamp("2026-01-02")]
    assert frame.loc[pd.Timestamp("2026-01-02"), "close"] == 70500.0


def test_krx_loader_uses_kosdaq_endpoint_for_kq_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_get(url: str, *, params: dict, headers: dict, timeout: float) -> _Resp:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return _Resp(
            {
                "OutBlock_1": [
                    {
                        "BAS_DD": "20260102",
                        "ISU_CD": "035720",
                        "TDD_OPNPRC": "50000",
                        "TDD_HGPRC": "51000",
                        "TDD_LWPRC": "49000",
                        "TDD_CLSPRC": "50500",
                        "ACC_TRDVOL": "1234",
                    },
                ]
            }
        )

    monkeypatch.setenv("KRX_OPEN_API_AUTH_KEY", "test-key")
    monkeypatch.setattr("backtest.loaders.krx.requests.get", fake_get)

    result = DataLoader().fetch(["035720.KQ"], "2026-01-02", "2026-01-02")

    assert result["035720.KQ"].loc[pd.Timestamp("2026-01-02"), "close"] == 50500.0
    assert calls[0]["url"].endswith("/svc/apis/sto/ksq_bydd_trd")


def test_krx_loader_rejects_intraday_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRX_OPEN_API_AUTH_KEY", "test-key")

    with pytest.raises(ValueError, match="daily"):
        DataLoader().fetch(["005930.KS"], "2026-01-02", "2026-01-05", interval="1H")
