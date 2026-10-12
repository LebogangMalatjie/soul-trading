import unittest
from datetime import datetime, timedelta, timezone

from news_bias.bias import build_bias
from news_bias.config import BiasEngineConfig, SymbolBiasConfig
from news_bias.executor import event_magic
from news_bias.history import ReactionStats, _percentile, compute_stats
from news_bias.plan import BrokerFacts, build_plan, compute_spike_buffer
from news_bias.scheduler import build_schedule, phase_at

UTC = timezone.utc


def facts(**over):
    base = dict(point=0.00001, tick_size=0.00001, tick_value=1.0, contract_size=100000,
                min_lot=0.01, max_lot=100.0, lot_step=0.01, stops_level_points=0, max_orders=10)
    base.update(over)
    return BrokerFacts(**base)


class BiasFormulaTests(unittest.TestCase):
    def test_strong_news_and_history_raises_probability(self):
        stats = ReactionStats(20, 0.8, 0.7, 50, 80, 5, 1)
        r = build_bias(event_key="NFP:1", event_type="NFP", symbol="XAUUSD",
                       news_score=0.8, news_reasons=["hot CPI"], news_sources=["http://x"],
                       stats=stats, min_probability_pct=55, min_history_sample=5)
        self.assertEqual(r.direction, "BUY")
        self.assertGreater(r.probability_pct, 70)
        self.assertIn("probability = clamp", r.formula)

    def test_insufficient_data_returns_no_trade(self):
        stats = ReactionStats(1, 0.0, 0.0, 0, 0, 0, 0)
        r = build_bias(event_key="CPI:1", event_type="CPI", symbol="XAUUSD",
                       news_score=0.9, news_reasons=[], news_sources=[],
                       stats=stats, min_probability_pct=55, min_history_sample=5,
                       news_available=False)
        self.assertEqual(r.direction, "NO_TRADE")

    def test_bearish_news_maps_to_sell(self):
        stats = ReactionStats(10, 0.7, 0.6, 40, 70, 4, 1)
        r = build_bias(event_key="NFP:2", event_type="NFP", symbol="XAUUSD",
                       news_score=-0.7, news_reasons=["weak jobs"], news_sources=["http://y"],
                       stats=stats, min_probability_pct=55, min_history_sample=5)
        self.assertEqual(r.direction, "SELL")


class HistoryStatsTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(_percentile([10, 20, 30, 40], 50), 25.0)
        self.assertEqual(_percentile([], 80), 0.0)

    def test_hit_rates(self):
        rows = [
            {"surprise": 1, "expected_dir": "BUY", "first_1m_dir": "BUY", "m15_dir": "BUY",
             "first_1m_points": 30, "fakeout_points": 5, "spread_points": 2},
            {"surprise": 1, "expected_dir": "BUY", "first_1m_dir": "SELL", "m15_dir": "BUY",
             "first_1m_points": 10, "fakeout_points": 8, "spread_points": 3},
        ]
        s = compute_stats(rows)
        self.assertEqual(s.sample_size, 2)
        self.assertEqual(s.first_candle_hit_rate, 0.5)
        self.assertEqual(s.m15_hit_rate, 1.0)


class OrderTypeTests(unittest.TestCase):
    def test_buy_bias_places_stops_above_price(self):
        plan = build_plan(symbol="XAUUSD", direction="BUY", reference_price=2000.0, facts=facts(),
                          cfg=SymbolBiasConfig(), engine_cfg=BiasEngineConfig(),
                          atr14_5m=2.0, atr5_5m=1.0, avg_release_spread=1.0, fakeout_points=5.0,
                          p80_move_points=50.0, avg_move_points=30.0, free_margin=100000.0,
                          margin_per_lot=100.0, zar_rate=18.0)
        self.assertTrue(all(o.order_type == "BUY_STOP" for o in plan.orders))
        self.assertTrue(all(o.entry_price > 2000.0 for o in plan.orders))

    def test_sell_bias_places_stops_below_price(self):
        plan = build_plan(symbol="XAUUSD", direction="SELL", reference_price=2000.0, facts=facts(),
                          cfg=SymbolBiasConfig(), engine_cfg=BiasEngineConfig(),
                          atr14_5m=2.0, atr5_5m=1.0, avg_release_spread=1.0, fakeout_points=5.0,
                          p80_move_points=50.0, avg_move_points=30.0, free_margin=100000.0,
                          margin_per_lot=100.0, zar_rate=18.0)
        self.assertTrue(all(o.order_type == "SELL_STOP" for o in plan.orders))
        self.assertTrue(all(o.entry_price < 2000.0 for o in plan.orders))


class MinDistanceTests(unittest.TestCase):
    def test_buffer_is_max_of_components(self):
        cfg = SymbolBiasConfig(atr_mult=1.0, spread_mult=10.0, stops_level_margin_points=5.0,
                               fakeout_mult=1.0)
        buf = compute_spike_buffer(cfg, atr14_5m=0.0001, avg_release_spread=1.0,
                                   stops_level_points=0, fakeout_points=50.0, point=0.00001)
        self.assertAlmostEqual(buf, 0.0005, places=8)


class R15kSizingTests(unittest.TestCase):
    def _plan(self, **over):
        kwargs = dict(symbol="EURUSD", direction="BUY", reference_price=1.1, facts=facts(),
                      cfg=SymbolBiasConfig(), engine_cfg=BiasEngineConfig(target_zar=15000.0),
                      atr14_5m=0.0005, atr5_5m=0.0003, avg_release_spread=1.0, fakeout_points=5.0,
                      p80_move_points=50.0, avg_move_points=30.0, free_margin=1e9,
                      margin_per_lot=100.0, zar_rate=18.0)
        kwargs.update(over)
        return build_plan(**kwargs)

    def test_basket_reaches_target_at_target_level(self):
        plan = self._plan()
        self.assertGreater(plan.achieved_target_zar, 14000)
        self.assertLessEqual(plan.achieved_target_zar, 15600)

    def test_max_volume_split_caps_lots(self):
        plan = self._plan(facts=facts(max_lot=0.5))
        self.assertTrue(all(o.lots <= 0.5 + 1e-9 for o in plan.orders))

    def test_margin_shortfall_scales_down_and_notes(self):
        plan = self._plan(free_margin=500.0, margin_per_lot=100.0)
        self.assertTrue(any("margin" in n.lower() for n in plan.notes))

    def test_infeasible_when_tick_value_zero(self):
        plan = self._plan(facts=facts(tick_value=0.0))
        self.assertFalse(plan.feasible)


class SchedulerTests(unittest.TestCase):
    def test_schedule_points(self):
        ev = datetime(2026, 10, 13, 12, 30, tzinfo=UTC)
        s = build_schedule(ev)
        self.assertEqual(len(s.regen_times), 3)
        self.assertEqual(s.lock_time, ev - timedelta(minutes=5))
        self.assertEqual(s.cutoff_time, ev - timedelta(seconds=60))

    def test_phase_progression(self):
        ev = datetime(2026, 10, 13, 12, 30, tzinfo=UTC)
        s = build_schedule(ev)
        self.assertEqual(phase_at(s, ev - timedelta(minutes=40)), "idle")
        self.assertEqual(phase_at(s, ev - timedelta(minutes=10)), "regen")
        self.assertEqual(phase_at(s, ev - timedelta(minutes=2)), "await_confirm")
        self.assertEqual(phase_at(s, ev + timedelta(minutes=5)), "live")
        self.assertEqual(phase_at(s, ev + timedelta(minutes=20)), "expired")


class ExecutorTests(unittest.TestCase):
    def test_event_magic_is_stable_and_distinct(self):
        a = event_magic("NFP:1", "XAUUSD")
        self.assertEqual(a, event_magic("NFP:1", "XAUUSD"))
        self.assertNotEqual(a, event_magic("NFP:1", "EURUSD"))


if __name__ == "__main__":
    unittest.main()

