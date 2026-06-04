"""Curated read/write classification for KIS Open API operations."""

from __future__ import annotations

from src.live.classification import ToolClass

KIS_TOOL_CLASS: dict[str, ToolClass] = {
    "inquire_price": ToolClass.READ,
    "inquire_balance": ToolClass.READ,
    "inquire_psbl_order": ToolClass.READ,
    "inquire_daily_itemchartprice": ToolClass.READ,
    "asking_price_krx": ToolClass.READ,
    "ccnl_krx": ToolClass.READ,
    "order_cash": ToolClass.WRITE,
    "order_rvsecncl": ToolClass.WRITE,
    "order_credit": ToolClass.WRITE,
}

