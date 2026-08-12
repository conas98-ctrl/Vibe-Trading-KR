"""Local market data tool backed by the shared loader layer."""

from __future__ import annotations

from typing import Any

from src.agent.tools import BaseTool
from src.market_data import DEFAULT_MAX_ROWS, fetch_market_data_json


class MarketDataTool(BaseTool):
    """Fetch normalized OHLCV data through repository loaders."""

    name = "get_market_data"
    description = (
        "Fetch normalized OHLCV market data through the repository loader layer. "
        "For Korean equities, pass market=kr; configured pykrx MCP OHLCV is primary "
        "and successful price bars are source-locked against other providers. Its "
        "as_of/latest_ohlcv/derived/provenance summary is authoritative; do not call "
        "raw pykrx OHLCV again after success. "
        "Use this for stock, ETF, index, or crypto price bars before writing raw "
        "yfinance/OKX/Tushare scripts."
    )
    parameters = {
        "type": "object",
        "properties": {
            "codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'Symbols such as ["AAPL.US"], ["700.HK"], ["BTC-USDT"].',
            },
            "start_date": {
                "type": "string",
                "description": "Start date in YYYY-MM-DD format.",
            },
            "end_date": {
                "type": "string",
                "description": "End date in YYYY-MM-DD format.",
            },
            "source": {
                "type": "string",
                "description": "Data source: auto, yfinance, okx, tushare, akshare, or ccxt.",
                "default": "auto",
            },
            "market": {
                "type": "string",
                "enum": ["auto", "kr"],
                "description": "Market hint. Use kr for a bare six-digit Korean ticker.",
                "default": "auto",
            },
            "fields": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["ohlcv", "derived", "fundamentals", "market_cap", "investor_flow"],
                },
                "description": "Optional Korean analysis groups; OHLCV is always fetched first.",
            },
            "interval": {
                "type": "string",
                "description": "Bar size, e.g. 1D, 1H, 4H, 30m.",
                "default": "1D",
            },
            "max_rows": {
                "type": "integer",
                "description": "Per-symbol row cap. Use 0 only when the full series is required.",
                "default": DEFAULT_MAX_ROWS,
            },
        },
        "required": ["codes", "start_date", "end_date"],
    }

    def execute(self, **kwargs: Any) -> str:
        return fetch_market_data_json(
            codes=kwargs["codes"],
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            source=kwargs.get("source", "auto"),
            interval=kwargs.get("interval", "1D"),
            max_rows=kwargs.get("max_rows", DEFAULT_MAX_ROWS),
            market=kwargs.get("market", "auto"),
            fields=kwargs.get("fields"),
        )
