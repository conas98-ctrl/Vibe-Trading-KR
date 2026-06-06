"""Credential-gated Korean data-source smoke contracts."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.loaders import kr_data_smoke


class _FakeDailyLoader:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.fetch_calls: list[dict] = []

    def is_available(self) -> bool:
        return self.available

    def fetch(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        self.fetch_calls.append(
            {
                "codes": codes,
                "start_date": start_date,
                "end_date": end_date,
                "interval": interval,
            }
        )
        return {
            codes[0]: pd.DataFrame(
                {"close": [70500.0]},
                index=[pd.Timestamp(start_date)],
            )
        }


class _FakeKoscomLoader(_FakeDailyLoader):
    def __init__(self, *, available: bool = True) -> None:
        super().__init__(available=available)
        self.holiday_calls: list[dict] = []

    def fetch_holidays(self, *, nation_code: str = "KR") -> set[pd.Timestamp]:
        self.holiday_calls.append({"nation_code": nation_code})
        return {pd.Timestamp("2026-01-01").date()}


def test_build_smoke_plan_lists_sources_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KRX_OPEN_API_AUTH_KEY", "secret-krx")
    monkeypatch.setenv("KOSCOM_OPEN_API_KEY", "secret-koscom")

    plan = kr_data_smoke.build_smoke_plan(
        loader_factories={
            "krx": lambda: _FakeDailyLoader(available=True),
            "koscom": lambda: _FakeKoscomLoader(available=True),
        }
    )

    assert plan["status"] == "planned"
    assert plan["allow_data_calls_required"] is True
    assert [step["operation"] for step in plan["steps"]] == [
        "krx_daily",
        "koscom_daily",
        "koscom_holidays",
    ]
    assert {source["source"] for source in plan["sources"]} == {"krx", "koscom"}
    assert all(source["configured"] is True for source in plan["sources"])
    assert "secret-krx" not in str(plan)
    assert "secret-koscom" not in str(plan)


def test_run_smoke_refuses_data_calls_without_explicit_opt_in() -> None:
    krx_loader = _FakeDailyLoader()
    koscom_loader = _FakeKoscomLoader()

    result = kr_data_smoke.run_smoke(
        allow_data_calls=False,
        loader_factories={
            "krx": lambda: krx_loader,
            "koscom": lambda: koscom_loader,
        },
    )

    assert result["status"] == "not_run"
    assert result["plan"]["allow_data_calls_required"] is True
    assert krx_loader.fetch_calls == []
    assert koscom_loader.fetch_calls == []
    assert koscom_loader.holiday_calls == []


def test_run_smoke_executes_read_only_data_checks_with_explicit_opt_in() -> None:
    krx_loader = _FakeDailyLoader()
    koscom_loader = _FakeKoscomLoader()

    result = kr_data_smoke.run_smoke(
        allow_data_calls=True,
        symbol="005930.KS",
        start_date="2026-01-02",
        end_date="2026-01-02",
        loader_factories={
            "krx": lambda: krx_loader,
            "koscom": lambda: koscom_loader,
        },
    )

    assert result["status"] == "passed"
    assert [check["operation"] for check in result["checks"]] == [
        "krx_daily",
        "koscom_daily",
        "koscom_holidays",
    ]
    assert krx_loader.fetch_calls == [
        {
            "codes": ["005930.KS"],
            "start_date": "2026-01-02",
            "end_date": "2026-01-02",
            "interval": "1D",
        }
    ]
    assert koscom_loader.fetch_calls == krx_loader.fetch_calls
    assert koscom_loader.holiday_calls == [{"nation_code": "KR"}]
    assert result["checks"][0]["rows"] == 1
    assert result["checks"][2]["holiday_count"] == 1


def test_run_smoke_blocks_missing_credentials_without_fetching() -> None:
    krx_loader = _FakeDailyLoader(available=False)

    result = kr_data_smoke.run_smoke(
        allow_data_calls=True,
        operations=["krx_daily"],
        loader_factories={"krx": lambda: krx_loader},
    )

    assert result["status"] == "blocked"
    assert result["checks"] == [
        {
            "operation": "krx_daily",
            "source": "krx",
            "status": "blocked",
            "reason": "credential_not_configured",
        }
    ]
    assert krx_loader.fetch_calls == []


def test_run_smoke_rejects_unsupported_operations() -> None:
    with pytest.raises(ValueError, match="unsupported smoke operation"):
        kr_data_smoke.run_smoke(operations=["unknown"])
