"""USD/JPY 自動売買ボット.

- 最小取引単位で新規建て (シンボル情報の minOpenOrderSize を使用)
- 含み益 >= TAKE_PROFIT_JPY で即時成行決済 (利確)
- 含み損 >= STOP_LOSS_JPY で即時成行決済 (損切り)
"""
import logging
import os
import time
from collections import deque

from .client import ApiError, GmoFxClient

log = logging.getLogger("fxbot")


def unrealized_pnl(position: dict, bid: float, ask: float) -> float:
    """現在レートでの評価損益(円)。買いは bid で、売りは ask で決済される前提。"""
    price, size = float(position["price"]), float(position["size"])
    if position["side"] == "BUY":
        pnl = (bid - price) * size
    else:
        pnl = (price - ask) * size
    return round(pnl, 2)  # 浮動小数誤差で 1999.9999.. となり閾値を逃すのを防ぐ


def exit_reason(pnl: float, take_profit: float, stop_loss: float):
    if pnl >= take_profit:
        return "TAKE_PROFIT"
    if pnl <= -stop_loss:
        return "STOP_LOSS"
    return None


class MomentumSignal:
    """直近 N ティックの短期/長期移動平均でエントリー方向を決める簡易シグナル."""

    def __init__(self, short: int = 5, long: int = 20):
        self.short, self.long = short, long
        self.prices = deque(maxlen=long)

    def update(self, mid: float):
        self.prices.append(mid)
        if len(self.prices) < self.long:
            return None
        p = list(self.prices)
        s, l = sum(p[-self.short:]) / self.short, sum(p) / self.long
        if s > l:
            return "BUY"
        if s < l:
            return "SELL"
        return None


class Bot:
    def __init__(self, client: GmoFxClient, symbol="USD_JPY", take_profit=2000.0,
                 stop_loss=1000.0, interval=1.0, dry_run=True, size=None):
        self.client = client
        self.symbol = symbol
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.interval = interval
        self.dry_run = dry_run
        self.size = size
        self.signal = MomentumSignal()
        self.paper_position = None  # dry-run 用の仮想建玉

    def setup(self):
        if self.size is None:
            rule = self.client.symbol_rule(self.symbol)
            self.size = int(rule["minOpenOrderSize"])
        log.info("symbol=%s size=%s TP=+%.0f円 SL=-%.0f円 dry_run=%s (1pip=%.0f円)",
                 self.symbol, self.size, self.take_profit, self.stop_loss, self.dry_run,
                 self.size * 0.01)

    def positions(self):
        if self.dry_run:
            return [self.paper_position] if self.paper_position else []
        return self.client.open_positions(self.symbol)

    def step(self):
        t = self.client.ticker(self.symbol)
        if t["status"] != "OPEN":
            log.debug("market closed")
            return
        bid, ask = t["bid"], t["ask"]
        positions = self.positions()

        if positions:
            for pos in positions:
                pnl = unrealized_pnl(pos, bid, ask)
                reason = exit_reason(pnl, self.take_profit, self.stop_loss)
                log.info("pos=%s %s %s@%s pnl=%.0f円", pos["positionId"], pos["side"],
                         pos["size"], pos["price"], pnl)
                if reason:
                    log.warning("%s: 決済 pnl=%.0f円", reason, pnl)
                    if self.dry_run:
                        self.paper_position = None
                    else:
                        self.client.close_position(self.symbol, pos)
            return

        side = self.signal.update((bid + ask) / 2)
        if side:
            log.warning("新規 %s %s", side, self.size)
            if self.dry_run:
                self.paper_position = {"positionId": "paper", "side": side, "size": self.size,
                                       "price": ask if side == "BUY" else bid}
            else:
                self.client.market_order(self.symbol, side, self.size)
            self.signal.prices.clear()

    def run(self):
        self.setup()
        while True:
            try:
                self.step()
            except ApiError as e:
                log.error("%s", e)
            except Exception:
                log.exception("unexpected error")
            time.sleep(self.interval)


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    dry_run = os.getenv("DRY_RUN", "1") != "0"
    key, secret = os.getenv("GMO_FX_API_KEY", ""), os.getenv("GMO_FX_SECRET_KEY", "")
    if not dry_run and not (key and secret):
        raise SystemExit("GMO_FX_API_KEY / GMO_FX_SECRET_KEY を設定してください")
    size = os.getenv("ORDER_SIZE")
    Bot(
        GmoFxClient(key, secret),
        symbol=os.getenv("SYMBOL", "USD_JPY"),
        take_profit=float(os.getenv("TAKE_PROFIT_JPY", "2000")),
        stop_loss=float(os.getenv("STOP_LOSS_JPY", "1000")),
        interval=float(os.getenv("INTERVAL_SEC", "1")),
        dry_run=dry_run,
        size=int(size) if size else None,
    ).run()


if __name__ == "__main__":
    main()
