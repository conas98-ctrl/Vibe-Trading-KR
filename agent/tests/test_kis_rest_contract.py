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
        if path == "/oauth2/Approval":
            return _Response({"approval_key": "approval-123"})
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
    assert kis.KIS_DOMESTIC_STOCK_ENDPOINTS["websocket_approval"]["path"] == "/oauth2/Approval"
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


def test_kis_websocket_catalog_matches_official_domestic_stock_samples() -> None:
    assert kis.KIS_WEBSOCKET_URLS == {
        "paper": "ws://ops.koreainvestment.com:31000",
        "live": "ws://ops.koreainvestment.com:21000",
    }
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_krx"]["tr_id"] == "H0STASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_nxt"]["tr_id"] == "H0NXASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["asking_price_total"]["tr_id"] == "H0UNASP0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_krx"]["tr_id"] == "H0STCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_nxt"]["tr_id"] == "H0NXCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_total"]["tr_id"] == "H0UNCNT0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_notice"]["live_tr_id"] == "H0STCNI0"
    assert kis.KIS_WEBSOCKET_CHANNELS["ccnl_notice"]["paper_tr_id"] == "H0STCNI9"
    assert kis.KIS_WEBSOCKET_CHANNELS["program_trade_total"]["tr_id"] == "H0UNPGM0"


def test_kis_websocket_approval_posts_official_approval_contract() -> None:
    client = _KisClient()
    approval_key = kis.issue_websocket_approval_key(_cfg(), client=client)
    assert approval_key == "approval-123"

    call = client.calls[-1]
    assert call["path"] == "/oauth2/Approval"
    assert call["json"] == {
        "grant_type": "client_credentials",
        "appkey": "app-key",
        "secretkey": "app-secret",
    }
    assert call["headers"]["Content-Type"] == "application/json"


def test_kis_websocket_url_and_subscribe_message_shape() -> None:
    assert kis.websocket_url(_cfg()) == "ws://ops.koreainvestment.com:31000"
    assert kis.websocket_url(_cfg(profile="live")) == "ws://ops.koreainvestment.com:21000"

    msg = kis.build_websocket_subscribe_message(
        "005930.KS",
        channel="ccnl_krx",
        approval_key="approval-123",
        config=_cfg(),
    )
    assert msg == {
        "header": {
            "content-type": "utf-8",
            "approval_key": "approval-123",
            "tr_type": "1",
            "custtype": "P",
        },
        "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}},
    }

    notice = kis.build_websocket_subscribe_message(
        "MYHTSID",
        channel="ccnl_notice",
        approval_key="approval-123",
        config=_cfg(),
    )
    assert notice["body"]["input"] == {"tr_id": "H0STCNI9", "tr_key": "MYHTSID"}

    live_notice = kis.build_websocket_subscribe_message(
        "MYHTSID",
        channel="ccnl_notice",
        approval_key="approval-123",
        config=_cfg(profile="live"),
    )
    assert live_notice["body"]["input"]["tr_id"] == "H0STCNI0"


def test_kis_parse_websocket_trade_and_system_frames() -> None:
    trade = kis.parse_websocket_message(
        "0|H0STCNT0|001|005930^153000^70000^2^1000^1.45^69500^69000^71000^68000^70100^70000^15",
        channel="ccnl_krx",
    )
    assert trade["type"] == "data"
    assert trade["tr_id"] == "H0STCNT0"
    assert trade["fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert trade["event"]["symbol"] == "005930"
    assert trade["event"]["last"] == 70000.0
    assert trade["event"]["trade_volume"] == 15.0

    system = kis.parse_websocket_message(
        (
            '{"header":{"tr_id":"H0STCNI9","tr_key":"MYHTSID","encrypt":"Y"},'
            '"body":{"rt_cd":"0","msg1":"SUBSCRIBE SUCCESS","output":{"iv":"iv-123","key":"key-123"}}}'
        )
    )
    assert system["type"] == "system"
    assert system["status"] == "ok"
    assert system["tr_id"] == "H0STCNI9"
    assert system["encrypted"] is True
    assert system["iv"] == "iv-123"
    assert system["key"] == "key-123"


def _kis_trade_values(
    *,
    symbol: str = "005930",
    time: str = "123929",
    price: str = "73100",
    trade_volume: str = "42",
    cumulative_volume: str = "1000",
    execution_side: str = "1",
) -> list[str]:
    values = [
        symbol,
        time,
        price,
        "2",
        "500",
        "0.69",
        "72050",
        "72000",
        "73500",
        "71000",
        "73100",
        "73000",
        trade_volume,
        cumulative_volume,
        "73000000",
        "12",
        "18",
        "6",
        "130.5",
        "600",
        "900",
        execution_side,
        "60.0",
        "110.5",
        "090000",
        "2",
        "1100",
        "123000",
        "2",
        "500",
        "091000",
        "2",
        "1000",
        "20260605",
        "20",
        "N",
        "300",
        "250",
        "3000",
        "2500",
        "5.5",
        "900",
        "111.1",
        "0",
        "0",
        "72000",
    ]
    assert len(values) == len(kis.KIS_WEBSOCKET_TRADE_FIELDS)
    return values


def test_kis_websocket_trade_parser_handles_official_multi_record_frame() -> None:
    first = _kis_trade_values()
    second = _kis_trade_values(
        symbol="000660",
        time="123930",
        price="121000",
        trade_volume="7",
        cumulative_volume="2000",
        execution_side="5",
    )

    ticks = kis.parse_websocket_trade_ticks(f"0|H0STCNT0|002|{'^'.join(first + second)}")

    assert [tick["symbol"] for tick in ticks] == ["005930", "000660"]
    assert ticks[0]["time"] == "123929"
    assert ticks[0]["last"] == 73100.0
    assert ticks[0]["trade_volume"] == 42.0
    assert ticks[0]["signed_trade_volume"] == 42.0
    assert ticks[0]["cumulative_volume"] == 1000.0
    assert ticks[0]["cumulative_trade_value"] == 73000000.0
    assert ticks[0]["ask"] == 73100.0
    assert ticks[0]["bid"] == 73000.0
    assert ticks[0]["trade_strength"] == 130.5
    assert ticks[0]["business_date"] == "20260605"
    assert ticks[0]["trading_halt"] is False
    assert ticks[0]["raw_fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert ticks[0]["raw_values"] == first
    assert ticks[1]["trade_volume"] == 7.0
    assert ticks[1]["signed_trade_volume"] == -7.0


def test_kis_websocket_trade_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected H0STCNT0"):
        kis.parse_websocket_trade_ticks("0|H0STASP0|001|005930")

    truncated = "^".join(_kis_trade_values()[:-1])
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 46 values per H0STCNT0 tick"):
        kis.parse_websocket_trade_ticks(f"0|H0STCNT0|001|{truncated}")


def _kis_orderbook_values(
    *,
    symbol: str = "005930",
    time: str = "123930",
    ask1: str = "73100",
    bid1: str = "73000",
    total_ask: str = "3000",
    total_bid: str = "2500",
) -> list[str]:
    asks = [str(int(ask1) + (level - 1) * 100) for level in range(1, 11)]
    bids = [str(int(bid1) - (level - 1) * 100) for level in range(1, 11)]
    ask_quantities = [str(100 * level) for level in range(1, 11)]
    bid_quantities = [str(90 * level) for level in range(1, 11)]
    values = [
        symbol,
        time,
        "0",
        *asks,
        *bids,
        *ask_quantities,
        *bid_quantities,
        total_ask,
        total_bid,
        "120",
        "90",
        "73100",
        "10",
        "500",
        "100",
        "2",
        "0.14",
        "12345",
        "5",
        "-3",
        "2",
        "-1",
        "00",
    ]
    assert len(values) == len(kis.KIS_WEBSOCKET_ORDERBOOK_FIELDS)
    return values


def test_kis_websocket_orderbook_parser_handles_official_multi_record_frame() -> None:
    first = _kis_orderbook_values()
    second = _kis_orderbook_values(
        symbol="000660",
        time="123931",
        ask1="121100",
        bid1="121000",
        total_ask="7000",
        total_bid="6500",
    )

    books = kis.parse_websocket_orderbooks(f"0|H0STASP0|002|{'^'.join(first + second)}")

    assert [book["symbol"] for book in books] == ["005930", "000660"]
    assert books[0]["time"] == "123930"
    assert books[0]["asks"][0] == {"level": 1, "price": 73100.0, "quantity": 100.0}
    assert books[0]["asks"][-1] == {"level": 10, "price": 74000.0, "quantity": 1000.0}
    assert books[0]["bids"][0] == {"level": 1, "price": 73000.0, "quantity": 90.0}
    assert books[0]["bids"][-1] == {"level": 10, "price": 72100.0, "quantity": 900.0}
    assert books[0]["total_ask_quantity"] == 3000.0
    assert books[0]["total_bid_quantity"] == 2500.0
    assert books[0]["overtime_total_ask_quantity"] == 120.0
    assert books[0]["anticipated_price"] == 73100.0
    assert books[0]["cumulative_volume"] == 12345.0
    assert books[0]["stock_deal_class_code"] == "00"
    assert books[0]["raw_fields"]["MKSC_SHRN_ISCD"] == "005930"
    assert books[0]["raw_values"] == first
    assert books[1]["asks"][0]["price"] == 121100.0
    assert books[1]["total_bid_quantity"] == 6500.0


def test_kis_websocket_orderbook_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected H0STASP0"):
        kis.parse_websocket_orderbooks("0|H0STCNT0|001|005930")

    truncated = "^".join(_kis_orderbook_values()[:-1])
    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 59 values per H0STASP0 book"):
        kis.parse_websocket_orderbooks(f"0|H0STASP0|001|{truncated}")


def _kis_notice_values(
    *,
    order_id: str = "0000012345",
    cntg_yn: str = "2",
    acpt_yn: str = "Y",
    rfus_yn: str = "N",
    quantity: str = "3",
    price: str = "70000",
) -> list[str]:
    return [
        "myhtsid",
        "12345678-01",
        order_id,
        "",
        "02",
        "1",
        "00",
        "",
        "005930",
        quantity,
        price,
        "153001",
        rfus_yn,
        cntg_yn,
        acpt_yn,
        "91234",
        "5",
        "TEST ACCOUNT",
        "0",
        "KRX",
        "Y",
        "",
        "",
        "",
        "20260604",
        "70000",
    ]


def test_kis_parse_websocket_order_notices_from_official_notice_fields() -> None:
    assert len(kis.KIS_WEBSOCKET_NOTICE_FIELDS) == 26
    assert kis.KIS_WEBSOCKET_NOTICE_FIELDS[13] == "CNTG_YN"
    assert kis.KIS_WEBSOCKET_NOTICE_FIELDS[-1] == "ODER_PRC"

    frame = "1|H0STCNI9|002|" + "^".join(
        _kis_notice_values(order_id="0000012345")
        + _kis_notice_values(order_id="0000012346", cntg_yn="1", acpt_yn="Y", rfus_yn="N", quantity="0", price="0")
    )

    notices = kis.parse_websocket_order_notices(frame)

    assert len(notices) == 2
    execution = notices[0]
    assert execution["kind"] == "order_notice"
    assert execution["tr_id"] == "H0STCNI9"
    assert execution["environment"] == "paper"
    assert execution["encrypted"] is True
    assert execution["customer_id"] == "myhtsid"
    assert execution["account"] == "12345678-01"
    assert execution["order_id"] == "0000012345"
    assert execution["symbol"] == "005930"
    assert execution["side"] == "buy"
    assert execution["notice_type"] == "execution"
    assert execution["execution_notice"] is True
    assert execution["execution_quantity"] == 3.0
    assert execution["execution_price"] == 70000.0
    assert execution["execution_time"] == "153001"
    assert execution["accepted"] is True
    assert execution["refused"] is False
    assert execution["order_quantity"] == 5.0
    assert execution["order_price"] == 70000.0
    assert execution["execution_date"] == "20260604"
    assert execution["raw_fields"]["CNTG_YN"] == "2"
    assert len(execution["raw_values"]) == 26

    accepted = notices[1]
    assert accepted["notice_type"] == "order_status"
    assert accepted["execution_notice"] is False
    assert accepted["execution_quantity"] == 0.0


def test_kis_order_notice_parser_rejects_wrong_or_truncated_frames() -> None:
    with pytest.raises(kis.KoreanConnectorConfigError, match="H0STCNI"):
        kis.parse_websocket_order_notices("0|H0STCNT0|001|" + "^".join(_kis_notice_values()))

    with pytest.raises(kis.KoreanConnectorConfigError, match="expected 26 values"):
        kis.parse_websocket_order_notices("1|H0STCNI0|001|" + "^".join(_kis_notice_values()[:-1]))


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
