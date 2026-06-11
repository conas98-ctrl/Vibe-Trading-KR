"""Tests for loader registry and fallback chain logic."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from backtest.loaders.base import DataLoaderProtocol, NoAvailableSourceError
from backtest.loaders.registry import (
    FALLBACK_CHAINS,
    LOADER_REGISTRY,
    get_loader_cls_with_fallback,
    register,
    resolve_loader,
)


# ---------------------------------------------------------------------------
# Helpers — fake loaders
# ---------------------------------------------------------------------------


class _FakeAvailableLoader:
    name = "fake_available"
    markets = {"a_share"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {}


class _FakeUnavailableLoader:
    name = "fake_unavailable"
    markets = {"a_share"}
    requires_auth = True

    def is_available(self) -> bool:
        return False

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {}


class _FakeInitErrorLoader:
    """Mimics Tushare with a missing token: blows up inside ``__init__``."""

    name = "fake_init_error"
    markets = {"a_share"}
    requires_auth = True

    def __init__(self) -> None:
        raise RuntimeError("api init error — TUSHARE_TOKEN not set")

    def is_available(self) -> bool:  # pragma: no cover — never reached
        return False

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {}


class _FakeCryptoLoader:
    name = "fake_crypto"
    markets = {"crypto"}
    requires_auth = False

    def is_available(self) -> bool:
        return True

    def fetch(self, codes, start_date, end_date, *, interval="1D", fields=None):
        return {}


# ---------------------------------------------------------------------------
# @register decorator
# ---------------------------------------------------------------------------


class TestRegisterDecorator:
    def test_register_adds_to_registry(self) -> None:
        # Use a patched registry to avoid polluting global state
        with patch.dict(LOADER_REGISTRY, {}, clear=True):
            register(_FakeAvailableLoader)
            assert "fake_available" in LOADER_REGISTRY
            assert LOADER_REGISTRY["fake_available"] is _FakeAvailableLoader

    def test_register_returns_class_unchanged(self) -> None:
        with patch.dict(LOADER_REGISTRY, {}, clear=True):
            result = register(_FakeAvailableLoader)
            assert result is _FakeAvailableLoader


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_fake_loader_satisfies_protocol(self) -> None:
        assert isinstance(_FakeAvailableLoader(), DataLoaderProtocol)

    def test_missing_method_fails_protocol(self) -> None:
        class BadLoader:
            name = "bad"

        assert not isinstance(BadLoader(), DataLoaderProtocol)


# ---------------------------------------------------------------------------
# FALLBACK_CHAINS
# ---------------------------------------------------------------------------


class TestFallbackChains:
    def test_all_expected_markets_present(self) -> None:
        expected = {
            "a_share",
            "us_equity",
            "hk_equity",
            "kr_equity",
            "kr_derivative",
            "kr_bond",
            "kr_elw",
            "crypto",
            "futures",
            "fund",
            "macro",
            "forex",
        }
        assert expected == set(FALLBACK_CHAINS.keys())

    def test_chains_are_non_empty(self) -> None:
        for market, chain in FALLBACK_CHAINS.items():
            assert len(chain) > 0, f"Fallback chain for {market} is empty"

    def test_kr_equity_prefers_official_krx_koscom_then_public_fallbacks(self) -> None:
        assert FALLBACK_CHAINS["kr_equity"] == ["krx", "koscom", "yfinance", "akshare"]

    def test_crypto_chain_includes_yfinance_fallback(self) -> None:
        """yfinance is the third-tier fallback for crypto when OKX and CCXT fail."""
        assert "yfinance" in FALLBACK_CHAINS["crypto"]
        # OKX and CCXT should still be preferred
        assert FALLBACK_CHAINS["crypto"][:2] == ["okx", "ccxt"]
        assert FALLBACK_CHAINS["crypto"][-1] == "yfinance"


# ---------------------------------------------------------------------------
# resolve_loader
# ---------------------------------------------------------------------------


class TestResolveLoader:
    def test_returns_first_available(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_unavailable": _FakeUnavailableLoader,
            "fake_available": _FakeAvailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "a_share": ["fake_unavailable", "fake_available"],
            }):
                loader = resolve_loader("a_share")
                assert loader.name == "fake_available"

    def test_raises_when_none_available(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_unavailable": _FakeUnavailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "a_share": ["fake_unavailable"],
            }):
                with pytest.raises(NoAvailableSourceError):
                    resolve_loader("a_share")

    def test_unknown_market_raises(self) -> None:
        with patch.dict(LOADER_REGISTRY, {}, clear=True):
            with pytest.raises(NoAvailableSourceError):
                resolve_loader("martian_stocks")

    def test_kr_equity_falls_back_when_krx_auth_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from backtest.loaders.koscom import DataLoader as KoscomLoader
        from backtest.loaders.krx import DataLoader as KrxLoader
        from backtest.loaders.yfinance_loader import DataLoader as YfinanceLoader

        import backtest.loaders.yfinance_loader as yfinance_loader

        monkeypatch.delenv("KRX_OPEN_API_AUTH_KEY", raising=False)
        monkeypatch.delenv("VIBE_TRADING_KRX_AUTH_KEY", raising=False)
        monkeypatch.delenv("KOSCOM_OPEN_API_KEY", raising=False)
        monkeypatch.delenv("KOSCOM_CHECK_API_KEY", raising=False)
        monkeypatch.delenv("VIBE_TRADING_KOSCOM_API_KEY", raising=False)
        monkeypatch.setattr(yfinance_loader, "yf", object())
        with patch.dict(LOADER_REGISTRY, {
            "krx": KrxLoader,
            "koscom": KoscomLoader,
            "yfinance": YfinanceLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "kr_equity": ["krx", "koscom", "yfinance"],
            }):
                loader = resolve_loader("kr_equity")
                assert loader.name == "yfinance"

    def test_kr_equity_uses_koscom_when_krx_missing_and_koscom_key_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from backtest.loaders.koscom import DataLoader as KoscomLoader
        from backtest.loaders.krx import DataLoader as KrxLoader
        from backtest.loaders.yfinance_loader import DataLoader as YfinanceLoader

        monkeypatch.delenv("KRX_OPEN_API_AUTH_KEY", raising=False)
        monkeypatch.delenv("VIBE_TRADING_KRX_AUTH_KEY", raising=False)
        monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "test-key")
        with patch.dict(LOADER_REGISTRY, {
            "krx": KrxLoader,
            "koscom": KoscomLoader,
            "yfinance": YfinanceLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "kr_equity": ["krx", "koscom", "yfinance"],
            }):
                loader = resolve_loader("kr_equity")
                assert loader.name == "koscom"


# ---------------------------------------------------------------------------
# get_loader_cls_with_fallback
# ---------------------------------------------------------------------------


class TestGetLoaderWithFallback:
    def test_returns_requested_if_available(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_available": _FakeAvailableLoader,
        }, clear=True):
            cls = get_loader_cls_with_fallback("fake_available")
            assert cls is _FakeAvailableLoader

    def test_falls_back_when_unavailable(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_unavailable": _FakeUnavailableLoader,
            "fake_available": _FakeAvailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "a_share": ["fake_unavailable", "fake_available"],
            }):
                cls = get_loader_cls_with_fallback("fake_unavailable")
                assert cls is _FakeAvailableLoader

    def test_unknown_source_raises(self) -> None:
        with patch.dict(LOADER_REGISTRY, {}, clear=True):
            with pytest.raises(NoAvailableSourceError):
                get_loader_cls_with_fallback("nonexistent")

    def test_no_fallback_raises(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_unavailable": _FakeUnavailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {"a_share": ["fake_unavailable"]}):
                with pytest.raises(NoAvailableSourceError):
                    get_loader_cls_with_fallback("fake_unavailable")


# ---------------------------------------------------------------------------
# Issue #50 — loaders that explode in __init__ (e.g. Tushare with no token)
# must not poison the fallback chain.
# ---------------------------------------------------------------------------


class TestInitErrorFallback:
    def test_resolve_loader_skips_init_error(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_init_error": _FakeInitErrorLoader,
            "fake_available": _FakeAvailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "a_share": ["fake_init_error", "fake_available"],
            }):
                loader = resolve_loader("a_share")
                assert loader.name == "fake_available"

    def test_get_loader_cls_falls_back_when_requested_init_errors(self) -> None:
        with patch.dict(LOADER_REGISTRY, {
            "fake_init_error": _FakeInitErrorLoader,
            "fake_available": _FakeAvailableLoader,
        }, clear=True):
            with patch.dict(FALLBACK_CHAINS, {
                "a_share": ["fake_init_error", "fake_available"],
            }):
                cls = get_loader_cls_with_fallback("fake_init_error")
                assert cls is _FakeAvailableLoader
