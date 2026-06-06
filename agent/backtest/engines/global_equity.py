"""Global equity (US / HK / KR) backtest engine.

Market rules:
  US:
    - T+0, long/short allowed
    - Zero commission (retail brokers)
    - Fractional shares supported (round to 0.01)
    - Low slippage (high liquidity)
  HK:
    - T+0, long/short allowed
    - Stamp tax 0.1% bilateral + levies
    - Lot-size rounding (simplified to 100 shares)
    - Higher slippage than US
  KR:
    - 1-share trading unit
    - Long-only by default
    - Daily price limit ±30% when bars expose ``pct_chg`` or ``pre_close``
    - Sell proceeds settle after T+2 trading bars before they can be reused
"""

from __future__ import annotations

import pandas as pd

from backtest.engines.base import BaseEngine
from backtest.engines.kr_market import KoreanTradingCalendar


class GlobalEquityEngine(BaseEngine):
    """US / HK / KR equity engine, selected by *market* parameter.

    Config keys:
      - slippage_us: default 0.0005
      - slippage_hk: default 0.001
      - slippage_kr: default 0.001
      - hk_stamp_tax: default 0.001 (0.1% bilateral)
      - hk_commission: default 0.00015 (万1.5)
      - hk_levy: default 0.0000565 (SFC + FRC)
      - hk_settlement: default 0.00002 (CCASS)
      - kr_commission: default 0.0 (broker-specific; configure explicitly)
      - kr_transaction_tax: default 0.0 (sell-side; configure explicitly)
      - kr_allow_short: default False
      - kr_settlement_lag_bars: default 2 (KRX stock cash settlement)
      - kr_holidays: default [] (KRX holiday dates supplied by caller)
      - kr_extra_closed_days: default [] (KRX-designated closure dates)
    """

    def __init__(self, config: dict, market: str = "us"):
        config = {**config, "leverage": config.get("leverage", 1.0)}
        super().__init__(config)
        self.market = market

        # US defaults
        self.slippage_us: float = config.get("slippage_us", 0.0005)
        # HK defaults
        self.slippage_hk: float = config.get("slippage_hk", 0.001)
        self.hk_stamp_tax: float = config.get("hk_stamp_tax", 0.001)
        self.hk_commission: float = config.get("hk_commission", 0.00015)
        self.hk_levy: float = config.get("hk_levy", 0.0000565)
        self.hk_settlement: float = config.get("hk_settlement", 0.00002)
        # KR defaults: market microstructure is stable, broker/tax rates are
        # configured explicitly because they vary by account/product/date.
        self.slippage_kr: float = config.get("slippage_kr", config.get("slippage", 0.001))
        self.kr_commission: float = config.get("kr_commission", 0.0)
        self.kr_transaction_tax: float = config.get("kr_transaction_tax", 0.0)
        self.kr_allow_short: bool = bool(config.get("kr_allow_short", False))
        self.kr_settlement_lag_bars: int = int(config.get("kr_settlement_lag_bars", 2))
        self.kr_calendar = KoreanTradingCalendar(
            holidays=config.get("kr_holidays", ()),
            extra_closed_days=config.get("kr_extra_closed_days", ()),
        )
        self._kr_unsettled_cash: list[tuple[pd.Timestamp, float]] = []
        self._kr_last_settlement_release_idx: int | None = None

    @property
    def kr_unsettled_cash(self) -> float:
        """KR sell proceeds that remain in equity but are not reusable cash."""
        return sum(amount for _, amount in self._kr_unsettled_cash)

    def on_bar(self, symbol: str, bar: pd.Series, timestamp: pd.Timestamp) -> None:
        """Release KR sell proceeds once their T+2 bar has arrived."""
        if self.market != "kr":
            return
        if self._kr_last_settlement_release_idx == self._bar_idx:
            return
        self._kr_last_settlement_release_idx = self._bar_idx
        due = [item for item in self._kr_unsettled_cash if item[0] <= pd.Timestamp(timestamp)]
        if not due:
            return
        self.capital += sum(amount for _, amount in due)
        self._kr_unsettled_cash = [
            item for item in self._kr_unsettled_cash if item[0] > pd.Timestamp(timestamp)
        ]

    def can_execute(self, symbol: str, direction: int, bar: pd.Series) -> bool:
        """US/HK/KR execution rules."""
        if self.market == "kr":
            if direction == -1 and not self.kr_allow_short:
                return False
            pct_chg = _calc_pct_change(bar)
            if pct_chg is not None:
                if direction == 1 and pct_chg >= 0.30 - 0.001:
                    return False
                if direction == 0 and pct_chg <= -0.30 + 0.001:
                    return False
        return True

    def round_size(self, raw_size: float, price: float) -> float:
        """US: fractional shares (0.01). HK: 100-share lots. KR: 1 share."""
        if self.market == "hk":
            return max(int(raw_size / 100) * 100, 0)
        if self.market == "kr":
            return max(int(raw_size), 0)
        return round(max(raw_size, 0.0), 2)

    def calc_commission(self, size: float, price: float, direction: int, is_open: bool) -> float:
        """US: zero commission. HK: stamp tax + levies.

        ``direction`` is reserved for future short-borrow fees
        (US Reg-T margin, HK SBL costs).
        """
        if self.market == "kr":
            notional = size * price
            comm = notional * self.kr_commission
            if (not is_open and direction == 1) or (is_open and direction == -1):
                comm += notional * self.kr_transaction_tax
            return comm
        if self.market == "hk":
            notional = size * price
            comm = notional * self.hk_commission       # broker commission
            comm += notional * self.hk_stamp_tax       # stamp tax bilateral
            comm += notional * self.hk_levy            # SFC + FRC levies
            comm += notional * self.hk_settlement      # CCASS settlement
            return comm
        # US: zero commission (SEC fee negligible)
        return 0.0

    def apply_slippage(self, price: float, direction: int) -> float:
        """US: low slippage. HK/KR: moderate slippage."""
        if self.market == "hk":
            rate = self.slippage_hk
        elif self.market == "kr":
            rate = self.slippage_kr
        else:
            rate = self.slippage_us
        return price * (1 + direction * rate)

    def _rebalance(
        self,
        symbol: str,
        target_weight: float,
        df: pd.DataFrame | None,
        ts: pd.Timestamp,
        equity: float,
    ) -> None:
        """Skip Korean equity rebalances on KRX/NXT closed days."""
        if self.market == "kr" and not self.kr_calendar.is_trading_day(ts):
            return
        super()._rebalance(symbol, target_weight, df, ts, equity)

    def _calc_equity(self, close_df: pd.DataFrame, ts: pd.Timestamp) -> float:
        """KR equity includes unsettled sell proceeds; free cash does not."""
        equity = super()._calc_equity(close_df, ts)
        if self.market == "kr":
            equity += self.kr_unsettled_cash
        return equity

    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: pd.Timestamp,
        reason: str,
    ) -> None:
        """Close KR long sales into a settlement queue instead of free cash."""
        if self.market != "kr" or self.kr_settlement_lag_bars <= 0:
            super()._close_position(symbol, exit_price, exit_time, reason)
            return

        pos = self.positions.get(symbol)
        net_sell_proceeds = 0.0
        if pos is not None and pos.direction == 1:
            exit_comm = self.calc_commission(pos.size, exit_price, pos.direction, is_open=False)
            net_sell_proceeds = max(pos.size * exit_price - exit_comm, 0.0)

        super()._close_position(symbol, exit_price, exit_time, reason)
        if net_sell_proceeds > 0:
            self.capital -= net_sell_proceeds
            self._kr_unsettled_cash.append(
                (
                    self.kr_calendar.add_trading_days(exit_time, self.kr_settlement_lag_bars),
                    net_sell_proceeds,
                )
            )


def _calc_pct_change(bar: pd.Series) -> float | None:
    """Calculate price change from either pct_chg or close/pre_close."""
    if "pct_chg" in bar.index:
        val = bar["pct_chg"]
        if pd.notna(val):
            return float(val) / 100.0

    close = bar.get("close")
    pre_close = bar.get("pre_close")
    if close is not None and pre_close is not None and pre_close > 0:
        return (float(close) - float(pre_close)) / float(pre_close)
    return None
