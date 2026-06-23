"""Unit tests for AlertEngine."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from watchtower.alert_engine import AlertEngine
from watchtower.classifier import AlertEvent, StockState, LevelState
from watchtower.price_providers.base import PriceQuote


def _make_price(symbol: str, price: float) -> PriceQuote:
    return PriceQuote(symbol=symbol, price=price, timestamp=datetime.now(), source="test")


def _touch_event(symbol="RELIANCE", level=1280.0, level_type="support", price=1280.0):
    return AlertEvent(
        stock=symbol, level=level, level_type=level_type,
        distance_pct=0.0, alert_reason="touch",
        current_price=price, timestamp=datetime.now()
    )


def _approaching_event(symbol="RELIANCE", level=1280.0, level_type="support", price=1293.0):
    return AlertEvent(
        stock=symbol, level=level, level_type=level_type,
        distance_pct=1.0, alert_reason="approaching",
        current_price=price, timestamp=datetime.now()
    )


def _override_event(symbol="RELIANCE", level=1280.0, level_type="support", price=1270.0):
    return AlertEvent(
        stock=symbol, level=level, level_type=level_type,
        distance_pct=0.8, alert_reason="override",
        current_price=price, timestamp=datetime.now()
    )


WATCHLIST = {
    "RELIANCE": {
        "support": [1280],
        "resistance": [],
    }
}


class TestAlertEngine(unittest.TestCase):

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_touch_fires_notifier(self, mock_eval, mock_send):
        mock_eval.return_value = [_touch_event()]
        engine = AlertEngine(WATCHLIST)
        results = engine.process_prices({"RELIANCE": _make_price("RELIANCE", 1280.0)})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].alert_reason, "touch")
        mock_send.assert_called_once()

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_cooldown_suppresses_via_classifier(self, mock_eval, mock_send):
        # First poll: touch fires
        mock_eval.side_effect = [[_touch_event()], []]
        engine = AlertEngine(WATCHLIST)
        prices = {"RELIANCE": _make_price("RELIANCE", 1280.0)}
        engine.process_prices(prices)
        self.assertEqual(mock_send.call_count, 1)
        # Second poll: classifier returns nothing (cooldown handled inside classifier)
        results2 = engine.process_prices(prices)
        self.assertEqual(results2, [])
        self.assertEqual(mock_send.call_count, 1)

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_override_fires_despite_cooldown(self, mock_eval, mock_send):
        mock_eval.side_effect = [[_touch_event()], [_override_event()]]
        engine = AlertEngine(WATCHLIST)
        prices = {"RELIANCE": _make_price("RELIANCE", 1280.0)}
        engine.process_prices(prices)
        self.assertEqual(mock_send.call_count, 1)
        results2 = engine.process_prices(prices)
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0].alert_reason, "override")
        self.assertEqual(mock_send.call_count, 2)

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_missing_symbol_skipped(self, mock_eval, mock_send):
        engine = AlertEngine(WATCHLIST)
        results = engine.process_prices({})
        self.assertEqual(results, [])
        mock_eval.assert_not_called()
        mock_send.assert_not_called()

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_approaching_fires_once(self, mock_eval, mock_send):
        mock_eval.side_effect = [[_approaching_event()], []]
        engine = AlertEngine(WATCHLIST)
        prices = {"RELIANCE": _make_price("RELIANCE", 1293.0)}
        results1 = engine.process_prices(prices)
        self.assertEqual(len(results1), 1)
        self.assertEqual(results1[0].alert_reason, "approaching")
        self.assertEqual(mock_send.call_count, 1)
        results2 = engine.process_prices(prices)
        self.assertEqual(results2, [])
        self.assertEqual(mock_send.call_count, 1)

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_multiple_levels(self, mock_eval, mock_send):
        watchlist = {"RELIANCE": {"support": [1280, 1250], "resistance": []}}
        ev1 = _touch_event(level=1280.0)
        ev2 = _touch_event(level=1250.0)
        mock_eval.return_value = [ev1, ev2]
        engine = AlertEngine(watchlist)
        results = engine.process_prices({"RELIANCE": _make_price("RELIANCE", 1280.0)})
        self.assertEqual(len(results), 2)
        self.assertEqual(mock_send.call_count, 2)

    @patch("watchtower.alert_engine.send_alert")
    @patch("watchtower.alert_engine.evaluate_poll")
    def test_levels_config_format(self, mock_eval, mock_send):
        """evaluate_poll must receive levels in {"level": float} format, not raw floats."""
        mock_eval.return_value = []
        engine = AlertEngine(WATCHLIST)
        engine.process_prices({"RELIANCE": _make_price("RELIANCE", 1300.0)})
        _, kwargs = mock_eval.call_args
        levels_cfg = kwargs.get("levels_config") or mock_eval.call_args[0][3]
        self.assertIsInstance(levels_cfg["support"][0], dict)
        self.assertIn("level", levels_cfg["support"][0])
        self.assertEqual(levels_cfg["support"][0]["level"], 1280.0)


if __name__ == "__main__":
    unittest.main()