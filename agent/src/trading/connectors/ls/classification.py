"""Curated read/write classification for LS Securities OpenAPI operations."""

from __future__ import annotations

from src.live.classification import ToolClass

LS_TOOL_CLASS: dict[str, ToolClass] = {
    "stock_quote": ToolClass.READ,
    "stock_history": ToolClass.READ,
    "account_balance": ToolClass.READ,
    "open_orders": ToolClass.READ,
    "stock_order": ToolClass.WRITE,
    "cancel_order": ToolClass.WRITE,
    "modify_order": ToolClass.WRITE,
}
