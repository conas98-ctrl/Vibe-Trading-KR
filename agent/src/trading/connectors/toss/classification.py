"""Curated read/write classification for Toss Securities Open API operations."""

from __future__ import annotations

from src.live.classification import ToolClass

TOSS_TOOL_CLASS: dict[str, ToolClass] = {
    "issue_oauth2_token": ToolClass.READ,
    "get_orderbook": ToolClass.READ,
    "get_prices": ToolClass.READ,
    "get_trades": ToolClass.READ,
    "get_price_limits": ToolClass.READ,
    "get_candles": ToolClass.READ,
    "get_stocks": ToolClass.READ,
    "get_stock_warnings": ToolClass.READ,
    "get_exchange_rate": ToolClass.READ,
    "get_market_calendar": ToolClass.READ,
    "get_accounts": ToolClass.READ,
    "get_holdings": ToolClass.READ,
    "get_orders": ToolClass.READ,
    "get_order": ToolClass.READ,
    "get_buying_power": ToolClass.READ,
    "get_sellable_quantity": ToolClass.READ,
    "get_commissions": ToolClass.READ,
    "create_order": ToolClass.WRITE,
    "modify_order": ToolClass.WRITE,
    "cancel_order": ToolClass.WRITE,
}
