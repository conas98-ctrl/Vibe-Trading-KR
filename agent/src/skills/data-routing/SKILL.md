---
name: data-routing
category: data-source
description: Data source selection decision tree. Load this skill BEFORE any backtest or data-fetching task to choose the best available data source.
---

## Data Source Overview

| Source | Markets | Auth Required | Network | Skill |
|--------|---------|---------------|---------|-------|
| tushare | A-shares, funds, futures, macro | Yes (`TUSHARE_TOKEN`) | China network | tushare |
| akshare | A-shares, US, HK, futures, macro, forex | No | Unrestricted | akshare |
| yfinance | US stocks, HK stocks, ETFs | No | Needs Yahoo Finance access | yfinance |
| okx | Crypto (OKX exchange) | No | Needs okx.com access | okx-market |
| ccxt | Crypto (100+ exchanges) | No | Needs exchange access | ccxt |
| pykrx MCP | Korean equities | No KRX_ID/KRX_PW | Configured external MCP | data-routing |

## Decision Tree

### Backtest Scenario (writing config.json)

Use `source: "auto"` — the runner automatically routes by symbol pattern and falls back to alternative sources if the primary one is unavailable.

You do NOT need to specify a concrete data source in config.json unless the user explicitly asks for one.

### Analysis / Research Scenario (writing Python scripts)

1. Identify the market type from the user's request
2. Pick the source by priority:

**A-shares**: tushare (if TUSHARE_TOKEN is set) > akshare (free fallback)
**US stocks**: yfinance > akshare
**HK stocks**: yfinance > akshare
**Crypto**: okx (single exchange) > ccxt (multi-exchange)
**Futures**: tushare > akshare
**Macro / economics**: akshare > tushare
**Forex**: akshare > yfinance

### Korean equities (analysis / research only)

- Call `get_market_data(..., market="kr")`. The hint is required for a bare six-digit ticker because it can collide with an A-share code.
- Explicit Korean forms are `005930.KS`, `035720.KQ`, `KRX:005930`, `KOSPI:005930`, and `KOSDAQ:035720`.
- Price, OHLCV, and volume use the configured pykrx MCP `get_stock_ohlcv` tool first.
- Successful pykrx OHLCV is source-locked: do not query yfinance, akshare, Tushare, Naver, or another provider for the same price bars.
- After a successful Korean `get_market_data` response whose OHLCV provenance is `pykrx_mcp`, reuse its `as_of`, `latest_ohlcv`, OHLCV, and derived values. Do not call raw `mcp_pykrx_get_stock_ohlcv` again for that analysis, including when fundamentals, market cap, or investor flow is unavailable.
- If `as_of` or `latest_ohlcv.date` is today, the latest daily bar may still be intraday. Describe `close` as the current price, intraday current price, or provisional close rather than a confirmed close, and treat volume as cumulative intraday volume. In a Korean final answer include: "오늘 데이터는 장중 미완성 일봉일 수 있으며, 현재가·고가·저가·거래량은 장 마감 후 달라질 수 있습니다."
- MA20/60/120/200, period return, and average volume are computed from that locked pykrx OHLCV.
- Fundamentals, market cap, and investor flow are independent groups. A failure in one must not replace successful OHLCV or switch other groups away from pykrx.
- If no validated group-specific fallback exists, report the group as unavailable. Never invent values.
- In the final answer, state the returned provenance for OHLCV, derived indicators, and every fallback/unavailable group.

3. Load the corresponding skill for API details: `load_skill("akshare")`

### Availability Check

- **tushare**: check if `TUSHARE_TOKEN` environment variable exists
- **yfinance / okx / ccxt / akshare**: free but may have network restrictions
- If the user reports "connection timeout" or "cannot access", switch to the same-market fallback

## Symbol Format Reference

| Market | Format | Examples |
|--------|--------|---------|
| A-shares | `NNNNNN.SZ/SH/BJ` | 000001.SZ, 600000.SH |
| US stocks | `TICKER.US` | AAPL.US, MSFT.US |
| HK stocks | `NNN(N).HK` | 700.HK, 9988.HK |
| Crypto | `SYMBOL-USDT` | BTC-USDT, ETH-USDT |
| Futures | `XXNNNN.EXCHANGE` | CU2406.SHFE |
| Forex | `XXX/YYY` | USD/CNY, EUR/USD |

## Fallback Chain (Runner Layer)

The backtest runner implements automatic fallback at the market level:

```
User requests 000001.SZ (A-share)
  -> detect market: a_share
  -> try tushare: TUSHARE_TOKEN missing -> skip
  -> try akshare: available -> use akshare
  -> success (zero config required)
```

This is transparent to the user — they just see results.
