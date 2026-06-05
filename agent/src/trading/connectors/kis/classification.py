"""Curated read/write classification for KIS Open API operations."""

from __future__ import annotations

from src.live.classification import ToolClass

KIS_TOOL_CLASS: dict[str, ToolClass] = {
    "inquire_price": ToolClass.READ,
    "inquire_balance": ToolClass.READ,
    "inquire_psbl_order": ToolClass.READ,
    "inquire_daily_itemchartprice": ToolClass.READ,
    "asking_price_krx": ToolClass.READ,
    "asking_price_nxt": ToolClass.READ,
    "asking_price_total": ToolClass.READ,
    "ccnl_krx": ToolClass.READ,
    "ccnl_notice": ToolClass.READ,
    "ccnl_nxt": ToolClass.READ,
    "ccnl_total": ToolClass.READ,
    "exp_ccnl_krx": ToolClass.READ,
    "exp_ccnl_nxt": ToolClass.READ,
    "exp_ccnl_total": ToolClass.READ,
    "index_ccnl": ToolClass.READ,
    "index_exp_ccnl": ToolClass.READ,
    "index_program_trade": ToolClass.READ,
    "market_status_krx": ToolClass.READ,
    "market_status_nxt": ToolClass.READ,
    "market_status_total": ToolClass.READ,
    "member_krx": ToolClass.READ,
    "member_nxt": ToolClass.READ,
    "member_total": ToolClass.READ,
    "overtime_asking_price_krx": ToolClass.READ,
    "overtime_ccnl_krx": ToolClass.READ,
    "overtime_exp_ccnl_krx": ToolClass.READ,
    "program_trade_krx": ToolClass.READ,
    "program_trade_nxt": ToolClass.READ,
    "program_trade_total": ToolClass.READ,
    "order_cash": ToolClass.WRITE,
    "order_rvsecncl": ToolClass.WRITE,
    "order_credit": ToolClass.WRITE,
}
