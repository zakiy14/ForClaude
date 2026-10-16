import unittest

from fxbot.bot import Bot, exit_reason, unrealized_pnl


class FakeClient:
    def __init__(self):
        self.bid, self.ask = 150.000, 150.002
        self.positions, self.orders, self.closes = [], [], []

    def ticker(self, symbol):
        return {"bid": self.bid, "ask": self.ask, "status": "OPEN"}

    def symbol_rule(self, symbol):
        return {"minOpenOrderSize": "10000"}

    def open_positions(self, symbol):
        return self.positions

    def market_order(self, symbol, side, size):
        self.orders.append((side, size))

    def close_position(self, symbol, pos):
        self.closes.append(pos["positionId"])
        self.positions.remove(pos)


class TestPnl(unittest.TestCase):
    def test_buy_pnl(self):
        pos = {"side": "BUY", "price": "150.000", "size": "10000"}
        self.assertAlmostEqual(unrealized_pnl(pos, 150.200, 150.202), 2000)

    def test_sell_pnl(self):
        pos = {"side": "SELL", "price": "150.000", "size": "10000"}
        self.assertAlmostEqual(unrealized_pnl(pos, 150.098, 150.100), -1000)

    def test_exit_reason(self):
        self.assertEqual(exit_reason(2000, 2000, 1000), "TAKE_PROFIT")
        self.assertEqual(exit_reason(-1000, 2000, 1000), "STOP_LOSS")
        self.assertIsNone(exit_reason(1999, 2000, 1000))
        self.assertIsNone(exit_reason(-999, 2000, 1000))


class TestBot(unittest.TestCase):
    def make(self):
        c = FakeClient()
        b = Bot(c, dry_run=False, interval=0)
        b.setup()
        return c, b

    def test_uses_min_size(self):
        _, b = self.make()
        self.assertEqual(b.size, 10000)

    def test_take_profit_closes(self):
        c, b = self.make()
        c.positions = [{"positionId": 1, "side": "BUY", "price": "149.800", "size": "10000"}]
        b.step()
        self.assertEqual(c.closes, [1])

    def test_stop_loss_closes(self):
        c, b = self.make()
        c.positions = [{"positionId": 2, "side": "BUY", "price": "150.100", "size": "10000"}]
        b.step()
        self.assertEqual(c.closes, [2])

    def test_hold_within_range(self):
        c, b = self.make()
        c.positions = [{"positionId": 3, "side": "BUY", "price": "150.050", "size": "10000"}]
        b.step()
        self.assertEqual(c.closes, [])

    def test_entry_after_signal(self):
        c, b = self.make()
        for i in range(20):
            c.bid, c.ask = 150 + i * 0.001, 150.002 + i * 0.001
            b.step()
        self.assertEqual(c.orders, [("BUY", 10000)])


if __name__ == "__main__":
    unittest.main()
