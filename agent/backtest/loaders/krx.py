"""KRX Data Marketplace official daily OHLCV loader.

The KRX OPEN API requires a Data Marketplace account, an authentication key,
and per-service usage approval. This loader is therefore fail-closed unless a
KRX auth key is configured.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

_BASE_URL = "https://data-dbg.krx.co.kr"
_KOSPI_DAILY_PATH = "/svc/apis/sto/stk_bydd_trd"
_KOSDAQ_DAILY_PATH = "/svc/apis/sto/ksq_bydd_trd"
_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_ENV_KEYS = ("KRX_OPEN_API_AUTH_KEY", "VIBE_TRADING_KRX_AUTH_KEY")


def _auth_key_from_env() -> str:
    for key in _ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _normalize_krx_symbol(code: str) -> tuple[str, str]:
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
    """Fetch KRX official daily stock OHLCV through Data Marketplace OPEN API."""

    name = "krx"
    markets = {"kr_equity"}
    requires_auth = True

    def __init__(self, auth_key: str | None = None, *, base_url: str = _BASE_URL) -> None:
        self.auth_key = (auth_key or _auth_key_from_env()).strip()
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Available only after a KRX OPEN API auth key is configured."""
        return bool(self.auth_key)

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch official KRX daily stock OHLCV keyed by original symbol."""
        del fields
        if str(interval or "1D").upper() != "1D":
            raise ValueError("KRX Data Marketplace loader currently supports daily bars only")
        if not codes:
            return {}
        validate_date_range(start_date, end_date)
        if not self.is_available():
            raise RuntimeError("KRX OPEN API auth key is required")

        dates = pd.date_range(start_date, end_date, freq="D")
        result: Dict[str, pd.DataFrame] = {}
        for requested in codes:
            market, issue_code = _normalize_krx_symbol(requested)
            rows: list[dict] = []
            for date in dates:
                rows.extend(self._fetch_daily_rows(market, date.strftime("%Y%m%d")))
            frame = _normalize_daily_rows(rows, issue_code)
            if not frame.empty:
                result[requested] = frame.loc[start_date:end_date]
        return result

    def _fetch_daily_rows(self, market: str, bas_dd: str) -> list[dict]:
        path = _KOSDAQ_DAILY_PATH if market == "kosdaq" else _KOSPI_DAILY_PATH
        response = requests.get(
            f"{self.base_url}{path}",
            params={"basDd": bas_dd},
            headers={"AUTH_KEY": self.auth_key},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("OutBlock_1") or payload.get("output") or payload.get("data") or []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]


def _normalize_daily_rows(rows: Iterable[dict], issue_code: str) -> pd.DataFrame:
    records = []
    for row in rows:
        row_issue = str(row.get("ISU_CD") or row.get("isuCd") or "").zfill(6)
        if row_issue != issue_code:
            continue
        trade_date = row.get("BAS_DD") or row.get("basDd")
        if not trade_date:
            continue
        records.append(
            {
                "trade_date": pd.Timestamp(str(trade_date)),
                "open": _to_number(row.get("TDD_OPNPRC") or row.get("open")),
                "high": _to_number(row.get("TDD_HGPRC") or row.get("high")),
                "low": _to_number(row.get("TDD_LWPRC") or row.get("low")),
                "close": _to_number(row.get("TDD_CLSPRC") or row.get("close")),
                "volume": _to_number(row.get("ACC_TRDVOL") or row.get("volume")),
            }
        )

    if not records:
        return pd.DataFrame(columns=_OHLCV_COLUMNS)
    frame = pd.DataFrame.from_records(records).set_index("trade_date").sort_index()
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    frame.index.name = "trade_date"
    return frame.loc[:, _OHLCV_COLUMNS].dropna(subset=["open", "high", "low", "close"])


def _to_number(value: object) -> float:
    return float(str(value or "0").replace(",", "").strip())
