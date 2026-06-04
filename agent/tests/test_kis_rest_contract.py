"""KIS official REST contract tests.

These tests lock the endpoint paths and TR IDs against the official
open-trading-api sample surface without requiring live KIS credentials.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from src.trading.connectors.kis import sdk as kis
from src.trading.connectors.kr_common import KoreanConnectorConfig

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _KisClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "json": json, "headers": headers or {}})
        if path == "/oauth2/tokenP":
            return _Response({"access_token": "token-123", "access_token_token_expired": "29991231235959"})
        if path == "/uapi/hashkey":
            return _Response({"HASH": "hash-123"})
        if path == "/uapi/domestic-stock/v1/trading/order-cash":
            return _Response({"rt_cd": "0", "output": {"ODNO": "00001", "KRX_FWDG_ORD_ORGNO": "91234"}})
        if path == "/uapi/domestic-stock/v1/trading/order-rvsecncl":
            return _Response({"rt_cd": "0", "output": {"ODNO": "00001", "KRX_FWDG_ORD_ORGNO": "91234"}})
        raise AssertionError(f"unexpected POST {path}")

    def get(self, url, *, params=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "GET", "path": path, "params": params or {}, "headers": headers or {}})
        if path == "/uapi/domestic-stock/v1/quotations/inquire-price":
            return _Response(
                {
                    "rt_cd": "0",
                    "output": {
                        "stck_prpr": "70000",
                        "prdy_vrss": "1000",
                        "prdy_ctrt": "1.45",
                        "acml_vol": "123456",
                        "acml_tr_pbmn": "8900000000",
                    },
                }
            )
        if path == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice":
            return _Response(
                {
                    "rt_cd": "0",
                    "output1": {"stck_shrn_iscd": "005930"},
                    "output2": [
                        {
                            "stck_bsop_date": "20260604",
                            "stck_oprc": "69000",
                            "stck_hgpr": "71000",
                            "stck_lwpr": "68000",
                            "stck_clpr": "70000",
                            "acml_vol": "1000",
                        }
                    ],
                }
            )
        if path == "/uapi/domestic-stock/v1/trading/inquire-balance":
            return _Response(
                {
                    "rt_cd": "0",
                    "output1": [{"pdno": "005930", "hldg_qty": "2", "evlu_amt": "140000"}],
                    "output2": [{"dnca_tot_amt": "500000", "tot_evlu_amt": "640000"}],
                },
                headers={"tr_cont": ""},
            )
        if path == "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl":
            return _Response(
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": "00001",
                            "ord_gno_brno": "91234",
                            "pdno": "005930",
                            "ord_qty": "5",
                            "tot_ccld_qty": "2",
                            "psbl_qty": "3",
                            "sll_buy_dvsn_cd": "02",
                            "ord_unpr": "70000",
                        }
                    ],
                    "ctx_area_fk100": "",
                    "ctx_area_nk100": "",
                },
                headers={"tr_cont": ""},
            )
        raise AssertionError(f"unexpected GET {path}")


def _cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(
        connector="kis",
        profile=profile,
        app_key="app-key",
        app_secret="app-secret",
        account="12345678",
        account_product_code="01",
        paper_url=kis.PAPER_URL,
        live_url=kis.LIVE_URL,
    )


def test_kis_catalog_matches_official_domestic_stock_samples() -> None:
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_price"]["path"] == (
        "/uapi/domestic-stock/v1/quotations/inquire-price"
    )
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_price"]["tr_id"] == "FHKST01010100"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_daily_itemchartprice"]["tr_id"] == "FHKST03010100"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_balance"]["paper_tr_id"] == "VTTC8434R"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_psbl_rvsecncl"]["path"] == (
        "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    )
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["inquire_psbl_rvsecncl"]["tr_id"] == "TTTC0084R"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["order_cash"]["paper_buy_tr_id"] == "VTTC0012U"
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["order_cash"]["live_sell_tr_id"] == "TTTC0011U"


def test_kis_quote_requests_token_and_official_quote_endpoint() -> None:
    client = _KisClient()
    out = kis.get_quote("005930.KS", config=_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "005930"
    assert out["quote"]["last"] == 70000.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/tokenP"
    assert token_call["json"]["appkey"] == "app-key"
    assert quote_call["path"] == "/uapi/domestic-stock/v1/quotations/inquire-price"
    assert quote_call["params"] == {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
    assert quote_call["headers"]["authorization"] == "Bearer token-123"
    assert quote_call["headers"]["tr_id"] == "FHKST01010100"


def test_kis_history_uses_daily_itemchartprice_contract() -> None:
    client = _KisClient()
    out = kis.get_historical_bars("KRX:005930", config=_cfg(), client=client, period="1d", limit=1)
    assert out["status"] == "ok"
    assert out["bars"][0]["date"] == "20260604"
    assert out["bars"][0]["close"] == 70000.0

    history_call = client.calls[-1]
    assert history_call["path"] == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    assert history_call["headers"]["tr_id"] == "FHKST03010100"
    assert history_call["params"]["FID_PERIOD_DIV_CODE"] == "D"
    assert history_call["params"]["FID_INPUT_ISCD"] == "005930"


def test_kis_account_snapshot_uses_paper_balance_tr_id() -> None:
    client = _KisClient()
    out = kis.get_account_snapshot(_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["positions"][0]["symbol"] == "005930"
    assert out["account"]["cash"] == 500000.0

    balance_call = client.calls[-1]
    assert balance_call["path"] == "/uapi/domestic-stock/v1/trading/inquire-balance"
    assert balance_call["headers"]["tr_id"] == "VTTC8434R"
    assert balance_call["params"]["CANO"] == "12345678"
    assert balance_call["params"]["ACNT_PRDT_CD"] == "01"


def test_kis_open_orders_use_psbl_rvsecncl_contract() -> None:
    client = _KisClient()
    out = kis.get_open_orders(_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["orders"] == [
        {
            "order_id": "00001",
            "broker_order_id": "91234:00001",
            "symbol": "005930",
            "side": "buy",
            "quantity": 5.0,
            "filled_quantity": 2.0,
            "remaining_quantity": 3.0,
            "cancelable_quantity": 3.0,
            "limit_price": 70000.0,
            "raw": {
                "odno": "00001",
                "ord_gno_brno": "91234",
                "pdno": "005930",
                "ord_qty": "5",
                "tot_ccld_qty": "2",
                "psbl_qty": "3",
                "sll_buy_dvsn_cd": "02",
                "ord_unpr": "70000",
            },
        }
    ]

    call = client.calls[-1]
    assert call["path"] == "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    assert call["headers"]["tr_id"] == "TTTC0084R"
    assert call["params"] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "INQR_DVSN_1": "1",
        "INQR_DVSN_2": "0",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }


def test_kis_place_order_hashes_and_posts_order_cash() -> None:
    client = _KisClient()
    out = kis.place_order(
        _cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
    )
    assert out["status"] == "ok"
    assert out["order_id"] == "00001"

    hash_call = client.calls[-2]
    order_call = client.calls[-1]
    assert hash_call["path"] == "/uapi/hashkey"
    assert order_call["path"] == "/uapi/domestic-stock/v1/trading/order-cash"
    assert order_call["headers"]["hashkey"] == "hash-123"
    assert order_call["headers"]["tr_id"] == "VTTC0012U"
    assert order_call["json"]["PDNO"] == "005930"
    assert order_call["json"]["ORD_DVSN"] == "00"
    assert order_call["json"]["ORD_QTY"] == "3"
    assert order_call["json"]["ORD_UNPR"] == "70000"


def test_kis_live_order_uses_live_sell_tr_id() -> None:
    client = _KisClient()
    kis.place_order(
        _cfg(profile="live"),
        symbol="005930",
        side="sell",
        quantity=1,
        order_type="market",
        client=client,
    )
    order_call = client.calls[-1]
    assert order_call["headers"]["tr_id"] == "TTTC0011U"
    assert order_call["json"]["ORD_DVSN"] == "01"
    assert order_call["json"]["ORD_UNPR"] == "0"


def test_kis_cancel_order_posts_rvsecncl_contract() -> None:
    client = _KisClient()
    out = kis.cancel_order(_cfg(), "91234:00001", client=client)
    assert out["status"] == "ok"

    cancel_call = client.calls[-1]
    assert cancel_call["path"] == "/uapi/domestic-stock/v1/trading/order-rvsecncl"
    assert cancel_call["headers"]["tr_id"] == "VTTC0013U"
    assert cancel_call["json"]["KRX_FWDG_ORD_ORGNO"] == "91234"
    assert cancel_call["json"]["ORGN_ODNO"] == "00001"
    assert cancel_call["json"]["RVSE_CNCL_DVSN_CD"] == "02"
    assert cancel_call["json"]["QTY_ALL_ORD_YN"] == "Y"
