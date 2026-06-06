"""Curated read/write classification for DB Securities Open API operations."""

from __future__ import annotations

from src.live.classification import ToolClass

DB_TOOL_CLASS: dict[str, ToolClass] = {
    "auth_token": ToolClass.READ,
    "stock_quote": ToolClass.READ,
    "overseas_stock_quote": ToolClass.READ,
    "account_balance": ToolClass.READ,
    "open_orders": ToolClass.READ,
    "websocket_trade": ToolClass.READ,
    "websocket_orderbook": ToolClass.READ,
    "websocket_order_accept": ToolClass.READ,
    "websocket_order_execution": ToolClass.READ,
    "websocket_disconnect_session": ToolClass.READ,
    "stock_order": ToolClass.WRITE,
    "overseas_stock_order": ToolClass.WRITE,
    "modify_order": ToolClass.WRITE,
    "cancel_order": ToolClass.WRITE,
}
