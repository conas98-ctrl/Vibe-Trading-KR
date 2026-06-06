"""Koscom OpenAPI/CHECK API official Korean market data loader.

Koscom market data APIs require a market-data license, platform approval, and
an API key. This loader therefore stays unavailable until credentials are
explicitly configured.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

_BASE_URL = "https://oap.k-mydata.org"
_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_ENV_KEYS = ("KOSCOM_OPEN_API_KEY", "KOSCOM_CHECK_API_KEY", "VIBE_TRADING_KOSCOM_API_KEY")


def _api_key_from_env() -> str:
    for key in _ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _normalize_koscom_symbol(code: str) -> tuple[str, str]:
    """Return ``(market, six_digit_code)`` for a Korean stock symbol."""
    upper = code.strip().upper()
    if upper.startswith("KOSDAQ:"):
        return "kosdaq", upper.removeprefix("KOSDAQ:").zfill(6)
    if upper.endswith(".KQ"):
        return "kosdaq", upper.removesuffix(".KQ").zfill(6)
    if upper.startswith("KOSPI:"):
        return "kospi", upper.removeprefix("KOSPI:").zfill(6)
    if upper.endswith(".KS"):
        return "kospi", upper.removesuffix(".KS").zfill(6)
    if upper.startswith("KRX:"):
        return "kospi", upper.removeprefix("KRX:").zfill(6)
    if upper.startswith("KR."):
        return "kospi", upper.removeprefix("KR.").zfill(6)
    return "kospi", upper.zfill(6)


@register
class DataLoader:
    """Fetch official Koscom v3 Korean stock daily history data."""

    name = "koscom"
    markets = {"kr_equity"}
    requires_auth = True

    def __init__(self, api_key: str | None = None, *, base_url: str = _BASE_URL) -> None:
        self.api_key = (api_key or _api_key_from_env()).strip()
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Available only after a Koscom OpenAPI/CHECK API key is configured."""
        return bool(self.api_key)

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch Koscom daily stock history keyed by original symbol."""
        del fields
        if str(interval or "1D").upper() != "1D":
            raise ValueError("Koscom OpenAPI loader currently supports daily bars only")
        if not codes:
            return {}
        validate_date_range(start_date, end_date)
        if not self.is_available():
            raise RuntimeError("Koscom OpenAPI/CHECK API key is required")

        result: Dict[str, pd.DataFrame] = {}
        for requested in codes:
            market, issue_code = _normalize_koscom_symbol(requested)
            rows = self._fetch_history_rows(market, issue_code)
            frame = _normalize_history_rows(rows, issue_code)
            if not frame.empty:
                result[requested] = frame.loc[start_date:end_date]
        return result

    def _fetch_history_rows(self, market: str, issue_code: str) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/v3/market/closed/{market}/{issue_code}/history",
            params={"apikey": self.api_key},
            timeout=20,
        )
        response.raise_for_status()
        return _extract_rows(response.json())

    def fetch_holidays(self, *, nation_code: str = "KR") -> set[date]:
        """Fetch country holiday dates from Koscom v3 market extra service."""
        if not self.is_available():
            raise RuntimeError("Koscom OpenAPI/CHECK API key is required")
        response = requests.get(
            f"{self.base_url}/v3/market/extra/stocks/{nation_code.upper()}/holiday",
            params={"apikey": self.api_key},
            timeout=20,
        )
        response.raise_for_status()
        return _normalize_holiday_rows(_extract_rows(response.json()))


def _extract_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("data"),
        payload.get("output"),
        payload.get("items"),
        payload.get("OutBlock_1"),
    ]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([
            result.get("list"),
            result.get("data"),
            result.get("items"),
        ])

    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    return []


def _normalize_history_rows(rows: Iterable[dict], issue_code: str) -> pd.DataFrame:
    records = []
    for row in rows:
        row_issue = _row_issue_code(row)
        if row_issue and row_issue != issue_code:
            continue
        trade_date = _pick(row, "trdDd", "tradeDate", "date", "basDd", "BAS_DD")
        if not trade_date:
            continue
        records.append(
            {
                "trade_date": pd.Timestamp(str(trade_date)),
                "open": _to_number(_pick(row, "opnPrc", "open", "TDD_OPNPRC")),
                "high": _to_number(_pick(row, "hgPrc", "high", "TDD_HGPRC")),
                "low": _to_number(_pick(row, "lwPrc", "low", "TDD_LWPRC")),
                "close": _to_number(_pick(row, "clPrc", "close", "TDD_CLSPRC")),
                "volume": _to_number(_pick(row, "accTrdVol", "volume", "ACC_TRDVOL")),
            }
        )

    if not records:
        return pd.DataFrame(columns=_OHLCV_COLUMNS)
    frame = pd.DataFrame.from_records(records).set_index("trade_date").sort_index()
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    frame.index.name = "trade_date"
    return frame.loc[:, _OHLCV_COLUMNS].dropna(subset=["open", "high", "low", "close"])


def _normalize_holiday_rows(rows: Iterable[dict]) -> set[date]:
    holidays: set[date] = set()
    for row in rows:
        value = _pick(
            row,
            "holidayDate",
            "holiDd",
            "trdDd",
            "calndDd",
            "date",
            "basDd",
            "BAS_DD",
        )
        if value:
            holidays.add(pd.Timestamp(str(value)).date())
    return holidays


def _row_issue_code(row: dict) -> str:
    value = _pick(row, "isuSrtCd", "issuecode", "issueCode", "ISU_CD")
    return str(value).zfill(6) if value not in (None, "") else ""


def _pick(row: dict, *keys: str) -> object:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _to_number(value: object) -> float:
    return float(str(value or "0").replace(",", "").strip())
