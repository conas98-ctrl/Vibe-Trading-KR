"""LS and Kiwoom official REST contract tests.

These tests pin the Korean broker REST paths, headers, and body fields found
in the official LS OpenAPI and Kiwoom OpenAPI guides. They use fake clients so
they do not require live credentials or network calls.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from src.trading.connectors.kiwoom import sdk as kiwoom
from src.trading.connectors.kr_common import KoreanConnectorConfig
from src.trading.connectors.ls import sdk as ls

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


class _LsClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, params=None, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append({"method": "POST", "path": path, "params": params or {}, "json": json, "headers": headers or {}})
        if path == "/oauth2/token":
            return _Response({"access_token": "token-ls", "token_type": "Bearer", "expires_in": 86400})
        if path == "/stock/market-data":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "t1101OutBlock": {
                        "shcode": "078020",
                        "price": 4545,
                        "change": 10,
                        "diff": "0.22",
                        "volume": 2702,
                    },
                }
            )
        if path == "/stock/accno":
            return _Response(
                {
                    "rsp_cd": "00000",
                    "t0424OutBlock": {"sunamt": 203287854, "tappamt": 203287854},
                    "t0424OutBlock1": [
                        {"expcode": "249420", "janqty": 1091, "price": 16400, "mamt": 67730600, "hname": "일동제약"}
                    ],
                }
            )
        if path == "/stock/order":
            tr_cd = (headers or {}).get("tr_cd", "")
            if tr_cd == "CSPAT00601":
                return _Response({"rsp_cd": "00040", "rsp_msg": "buy order accepted", "CSPAT00601OutBlock2": {"OrdNo": 32004}})
            if tr_cd == "CSPAT00801":
                return _Response({"rsp_cd": "00156", "rsp_msg": "cancel order accepted", "CSPAT00801OutBlock2": {"OrdNo": 84006}})
            raise AssertionError(f"unexpected LS stock/order tr_cd={tr_cd}")
        raise AssertionError(f"unexpected LS POST {path}")


class _KiwoomClient:
    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, *, json=None, headers=None, timeout=None):
        path = urlparse(url).path
        api_id = (headers or {}).get("api-id", "")
        self.calls.append({"method": "POST", "path": path, "json": json or {}, "headers": headers or {}})
        if path == "/oauth2/token":
            return _Response({"return_code": 0, "return_msg": "정상적으로 처리되었습니다", "token_type": "bearer", "token": "token-kw"})
        if path == "/api/dostk/stkinfo" and api_id == "ka10001":
            return _Response(
                {
                    "return_code": 0,
                    "stk_cd": "005930",
                    "cur_prc": "+70000",
                    "pred_pre": "+1000",
                    "flu_rt": "+1.45",
                    "trde_qty": "123456",
                    "open_pric": "+69000",
                    "high_pric": "+71000",
                    "low_pric": "+68000",
                }
            )
        if path == "/api/dostk/chart" and api_id == "ka10081":
            return _Response(
                {
                    "return_code": 0,
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {
                            "dt": "20260604",
                            "open_pric": "69000",
                            "high_pric": "71000",
                            "low_pric": "68000",
                            "cur_prc": "70000",
                            "trde_qty": "1000",
                        }
                    ],
                }
            )
        if path == "/api/dostk/acnt" and api_id == "kt00018":
            return _Response(
                {
                    "return_code": 0,
                    "tot_evlt_amt": "640000",
                    "prsm_dpst_aset_amt": "500000",
                    "acnt_evlt_remn_indv_tot": [
                        {"stk_cd": "A005930", "stk_nm": "삼성전자", "rmnd_qty": "2", "evlt_amt": "140000", "pur_pric": "69000"}
                    ],
                }
            )
        if path == "/api/dostk/acnt" and api_id == "ka10075":
            return _Response(
                {
                    "return_code": 0,
                    "oso": [{"ord_no": "1234567", "stk_cd": "005930", "ord_qty": "3", "ord_pric": "70000", "oso_qty": "1"}],
                }
            )
        if path == "/api/dostk/ordr" and api_id in {"kt10000", "kt10001", "kt10002", "kt10003"}:
            return _Response({"return_code": 0, "return_msg": "정상", "ord_no": "7654321", "dmst_stex_tp": "KRX"})
        raise AssertionError(f"unexpected Kiwoom POST {path} api-id={api_id}")


def _kiwoom_call(client: _KiwoomClient, api_id: str) -> dict:
    for call in client.calls:
        if call["headers"].get("api-id") == api_id:
            return call
    raise AssertionError(f"missing Kiwoom call api-id={api_id}")


def _ls_cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(connector="ls", profile=profile, app_key="app-key", app_secret="app-secret", paper_url=ls.PAPER_URL, live_url=ls.LIVE_URL)


def _kiwoom_cfg(profile="paper") -> KoreanConnectorConfig:
    return KoreanConnectorConfig(
        connector="kiwoom",
        profile=profile,
        app_key="app-key",
        app_secret="app-secret",
        paper_url=kiwoom.PAPER_URL,
        live_url=kiwoom.LIVE_URL,
    )


def test_ls_catalog_matches_official_openapi_samples() -> None:
    assert ls.LS_OPENAPI_ENDPOINTS["auth_token"]["path"] == "/oauth2/token"
    assert ls.LS_OPENAPI_ENDPOINTS["auth_token"]["content_type"] == "application/x-www-form-urlencoded"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_quote"]["path"] == "/stock/market-data"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_quote"]["tr_cd"] == "t1101"
    assert ls.LS_OPENAPI_ENDPOINTS["account_balance"]["path"] == "/stock/accno"
    assert ls.LS_OPENAPI_ENDPOINTS["account_balance"]["tr_cd"] == "t0424"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_order"]["path"] == "/stock/order"
    assert ls.LS_OPENAPI_ENDPOINTS["stock_order"]["tr_cd"] == "CSPAT00601"
    assert ls.LS_OPENAPI_ENDPOINTS["cancel_order"]["tr_cd"] == "CSPAT00801"


def test_ls_quote_requests_token_and_official_t1101_contract() -> None:
    client = _LsClient()
    out = ls.get_quote("078020.KS", config=_ls_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "078020"
    assert out["quote"]["last"] == 4545.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/token"
    assert token_call["params"] == {"grant_type": "client_credentials", "appkey": "app-key", "appsecretkey": "app-secret", "scope": "oob"}
    assert token_call["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert quote_call["path"] == "/stock/market-data"
    assert quote_call["headers"]["authorization"] == "Bearer token-ls"
    assert quote_call["headers"]["tr_cd"] == "t1101"
    assert quote_call["headers"]["tr_cont"] == "N"
    assert quote_call["headers"]["tr_cont_key"] == ""
    assert quote_call["json"] == {"t1101InBlock": {"shcode": "078020"}}


def test_ls_account_snapshot_uses_official_t0424_contract() -> None:
    client = _LsClient()
    out = ls.get_account_snapshot(_ls_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["account"]["cash"] == 203287854.0
    assert out["positions"][0]["symbol"] == "249420"
    assert out["positions"][0]["quantity"] == 1091.0

    balance_call = client.calls[-1]
    assert balance_call["path"] == "/stock/accno"
    assert balance_call["headers"]["tr_cd"] == "t0424"
    assert balance_call["json"] == {
        "t0424InBlock": {"prcgb": "", "chegb": "", "dangb": "", "charge": "", "cts_expcode": ""}
    }


def test_ls_order_and_cancel_use_official_stock_order_contracts() -> None:
    client = _LsClient()
    order = ls.place_order(
        _ls_cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
        exchange="KRX",
    )
    cancel = ls.cancel_order(_ls_cfg(), "32004", symbol="005930", quantity=3, client=client)
    assert order["status"] == "ok"
    assert order["order_id"] == "32004"
    assert cancel["status"] == "ok"

    order_call = next(call for call in client.calls if call["headers"].get("tr_cd") == "CSPAT00601")
    cancel_call = next(call for call in client.calls if call["headers"].get("tr_cd") == "CSPAT00801")
    assert order_call["path"] == "/stock/order"
    assert order_call["json"] == {
        "CSPAT00601InBlock1": {
            "IsuNo": "A005930",
            "OrdQty": 3,
            "OrdPrc": 70000,
            "BnsTpCode": "2",
            "OrdprcPtnCode": "00",
            "MgntrnCode": "000",
            "LoanDt": "",
            "OrdCndiTpCode": "0",
            "MbrNo": "KRX",
        }
    }
    assert cancel_call["json"] == {"CSPAT00801InBlock1": {"OrgOrdNo": 32004, "IsuNo": "A005930", "OrdQty": 3}}


def test_kiwoom_catalog_matches_official_openapi_guides() -> None:
    assert kiwoom.KIWOOM_REST_ENDPOINTS["auth_token"]["path"] == "/oauth2/token"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_info"]["path"] == "/api/dostk/stkinfo"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_info"]["api_id"] == "ka10001"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["daily_chart"]["path"] == "/api/dostk/chart"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["daily_chart"]["api_id"] == "ka10081"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["account_balance"]["api_id"] == "kt00018"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["open_orders"]["api_id"] == "ka10075"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_buy_order"]["api_id"] == "kt10000"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_sell_order"]["api_id"] == "kt10001"
    assert kiwoom.KIWOOM_REST_ENDPOINTS["stock_cancel_order"]["api_id"] == "kt10003"


def test_kiwoom_quote_requests_token_and_official_ka10001_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.get_quote("KRX:005930", config=_kiwoom_cfg(), client=client)
    assert out["status"] == "ok"
    assert out["symbol"] == "005930"
    assert out["quote"]["last"] == 70000.0

    token_call, quote_call = client.calls
    assert token_call["path"] == "/oauth2/token"
    assert token_call["json"] == {"grant_type": "client_credentials", "appkey": "app-key", "secretkey": "app-secret"}
    assert quote_call["path"] == "/api/dostk/stkinfo"
    assert quote_call["headers"]["authorization"] == "Bearer token-kw"
    assert quote_call["headers"]["api-id"] == "ka10001"
    assert quote_call["json"] == {"stk_cd": "005930"}


def test_kiwoom_history_uses_official_ka10081_daily_chart_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.get_historical_bars("005930.KS", config=_kiwoom_cfg(), client=client, limit=1, base_date="20260604")
    assert out["status"] == "ok"
    assert out["bars"][0]["date"] == "20260604"
    assert out["bars"][0]["close"] == 70000.0

    history_call = client.calls[-1]
    assert history_call["path"] == "/api/dostk/chart"
    assert history_call["headers"]["api-id"] == "ka10081"
    assert history_call["json"] == {"stk_cd": "005930", "base_dt": "20260604", "upd_stkpc_tp": "1"}


def test_kiwoom_account_and_open_orders_use_official_account_contracts() -> None:
    client = _KiwoomClient()
    snapshot = kiwoom.get_account_snapshot(_kiwoom_cfg(), client=client)
    orders = kiwoom.get_open_orders(_kiwoom_cfg(), client=client)
    assert snapshot["status"] == "ok"
    assert snapshot["account"]["total_value"] == 640000.0
    assert snapshot["positions"][0]["symbol"] == "005930"
    assert orders["status"] == "ok"
    assert orders["orders"][0]["order_id"] == "1234567"

    balance_call = _kiwoom_call(client, "kt00018")
    open_orders_call = _kiwoom_call(client, "ka10075")
    assert balance_call["path"] == "/api/dostk/acnt"
    assert balance_call["headers"]["api-id"] == "kt00018"
    assert balance_call["json"] == {"qry_tp": "1", "dmst_stex_tp": "KRX"}
    assert open_orders_call["headers"]["api-id"] == "ka10075"
    assert open_orders_call["json"] == {"all_stk_tp": "0", "trde_tp": "0", "stk_cd": ""}


def test_kiwoom_order_and_cancel_use_official_order_api_ids() -> None:
    client = _KiwoomClient()
    buy = kiwoom.place_order(
        _kiwoom_cfg(),
        symbol="005930",
        side="buy",
        quantity=3,
        order_type="limit",
        limit_price=70000,
        client=client,
        exchange="KRX",
    )
    sell = kiwoom.place_order(
        _kiwoom_cfg(),
        symbol="005930",
        side="sell",
        quantity=1,
        order_type="market",
        client=client,
        exchange="KRX",
    )
    cancel = kiwoom.cancel_order(_kiwoom_cfg(), "7654321", symbol="005930", quantity=0, client=client, exchange="KRX")
    assert buy["status"] == "ok"
    assert sell["status"] == "ok"
    assert cancel["status"] == "ok"

    buy_call = _kiwoom_call(client, "kt10000")
    sell_call = _kiwoom_call(client, "kt10001")
    cancel_call = _kiwoom_call(client, "kt10003")
    assert buy_call["path"] == "/api/dostk/ordr"
    assert buy_call["headers"]["api-id"] == "kt10000"
    assert buy_call["json"] == {"dmst_stex_tp": "KRX", "stk_cd": "005930", "ord_qty": "3", "ord_uv": "70000", "trde_tp": "0"}
    assert sell_call["headers"]["api-id"] == "kt10001"
    assert sell_call["json"]["trde_tp"] == "3"
    assert sell_call["json"]["ord_uv"] == ""
    assert cancel_call["headers"]["api-id"] == "kt10003"
    assert cancel_call["json"] == {"dmst_stex_tp": "KRX", "orig_ord_no": "7654321", "stk_cd": "005930", "cncl_qty": "0"}


def test_kiwoom_modify_order_uses_official_kt10002_contract() -> None:
    client = _KiwoomClient()
    out = kiwoom.modify_order(_kiwoom_cfg(), "7654321", symbol="005930", quantity=2, limit_price=71000, client=client, exchange="KRX")
    assert out["status"] == "ok"
    assert out["order_id"] == "7654321"

    modify_call = _kiwoom_call(client, "kt10002")
    assert modify_call["path"] == "/api/dostk/ordr"
    assert modify_call["json"] == {
        "dmst_stex_tp": "KRX",
        "orig_ord_no": "7654321",
        "stk_cd": "005930",
        "mdfy_qty": "2",
        "mdfy_uv": "71000",
        "mdfy_cond_uv": "",
    }
