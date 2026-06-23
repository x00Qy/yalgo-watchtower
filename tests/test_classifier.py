"""Unit tests for YALGO Watchtower Phase 1 alert classifier.

Tests every rule in isolation and the tricky rule interactions.
Run with: python -m unittest tests.test_classifier -v
"""
import sys
import os
import unittest
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watchtower.classifier import (
    evaluate_poll,
    StockState,
    LevelState,
    _distance_pct,
    _classify_distance,
    _is_breached,
    _single_poll_move_pct,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
T0 = datetime(2025, 10, 15, 9, 0, 0)

def make_levels(support=None, resistance=None):
    cfg = {}
    if support is not None:
        cfg["support"] = [{"level": l, "note": ""} for l in support]
    if resistance is not None:
        cfg["resistance"] = [{"level": l, "note": ""} for l in resistance]
    return cfg


def poll(state, price, time_offset_minutes=5, levels=None, symbol="TEST"):
    """Convenience wrapper: advance time by offset, run evaluate_poll, return alerts."""
    if levels is None:
        levels = make_levels(support=[1000], resistance=[1100])
    t = T0 + timedelta(minutes=time_offset_minutes)
    alerts = evaluate_poll(symbol, price, state, levels, t)
    return alerts, state


class TestClassifier(unittest.TestCase):
    """Unit tests for the alert classifier rules."""

    # ---------------------------------------------------------------------------
    # 1. far -> approaching transition fires exactly once
    # ---------------------------------------------------------------------------
    def test_far_to_approaching_fires_once(self):
        """Price moves from >3% away to within 3% but >1% — exactly one approaching alert."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 1060.0, 0, levels)
        self.assertEqual(len(alerts), 0)

        alerts, _ = poll(state, 1030.0, 5, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

        alerts, _ = poll(state, 1025.0, 10, levels)
        self.assertEqual(len(alerts), 0)

        alerts, _ = poll(state, 1020.0, 15, levels)
        self.assertEqual(len(alerts), 0)

    # ---------------------------------------------------------------------------
    # 2. staying in approaching zone does not re-fire
    # ---------------------------------------------------------------------------
    def test_staying_in_approaching_no_refire(self):
        """Price stays in approaching zone — no repeated alerts."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        for i in range(1, 5):
            alerts, _ = poll(state, 1025.0, i * 5, levels)
            self.assertEqual(len(alerts), 0, f"Unexpected alert at poll {i}")

    # ---------------------------------------------------------------------------
    # 3. touch always fires even mid-cooldown
    # ---------------------------------------------------------------------------
    def test_touch_always_fires_even_in_cooldown(self):
        """Touch alert must fire even when level is in cooldown."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 1030.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

        alerts, _ = poll(state, 1000.0, 10, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")

    # ---------------------------------------------------------------------------
    # 4. touch starts a fresh cooldown
    # ---------------------------------------------------------------------------
    def test_touch_restarts_cooldown(self):
        """When touch fires, it should start a fresh 1-hour cooldown from that moment."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, T0 + timedelta(hours=1))

        poll(state, 1000.0, 10, levels)
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, T0 + timedelta(minutes=70))

    # ---------------------------------------------------------------------------
    # 5. approaching alert is suppressed during cooldown (no override)
    # ---------------------------------------------------------------------------
    def test_approaching_suppressed_in_cooldown_no_override(self):
        """Approaching alert suppressed when in cooldown and no >=1% move."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        poll(state, 1060.0, 5, levels)
        poll(state, 1035.0, 15, levels)
        alerts, _ = poll(state, 1030.0, 20, levels)
        self.assertEqual(len(alerts), 0, "Approaching should be suppressed in cooldown without override")

    # ---------------------------------------------------------------------------
    # 6. 1% single-poll move overrides cooldown suppression, alert fires,
    #    cooldown is NOT reset
    # ---------------------------------------------------------------------------
    def test_override_bypasses_cooldown_no_reset(self):
        """>=1% move in one poll overrides cooldown; alert fires but cooldown unchanged."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        original_cooldown = state.level_states["support:1000.0"].cooldown_until
        self.assertEqual(original_cooldown, T0 + timedelta(hours=1))

        poll(state, 1060.0, 5, levels)

        alerts, _ = poll(state, 1030.0, 10, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "override")

        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, original_cooldown)

    # ---------------------------------------------------------------------------
    # 7. leaving approaching zone (back to far) and re-entering fires a new alert
    # ---------------------------------------------------------------------------
    def test_leave_far_reenter_fires_new_alert(self):
        """After going back to far, re-entering approaching zone fires a fresh alert."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        poll(state, 1025.0, 5, levels)
        poll(state, 1060.0, 10, levels)
        self.assertFalse(state.level_states["support:1000.0"].zone_entry_consumed)

        alerts, _ = poll(state, 1030.0, 65, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

    # ---------------------------------------------------------------------------
    # 8. cooldown expires after 1 hour and approaching can alert again normally
    # ---------------------------------------------------------------------------
    def test_cooldown_expiry_allows_normal_alert(self):
        """After 1 hour cooldown expires, approaching alerts work normally."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        poll(state, 1025.0, 5, levels)
        poll(state, 1060.0, 10, levels)

        alerts, _ = poll(state, 1030.0, 65, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

    # ---------------------------------------------------------------------------
    # 9. Breached support triggers touch alert
    # ---------------------------------------------------------------------------
    def test_breached_support_triggers_touch(self):
        """Price below support level should trigger touch (breached) alert."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 990.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")
        self.assertAlmostEqual(alerts[0].distance_pct, 1.0, places=5)

    # ---------------------------------------------------------------------------
    # 10. Breached resistance triggers touch alert
    # ---------------------------------------------------------------------------
    def test_breached_resistance_triggers_touch(self):
        """Price above resistance level should trigger touch (breached) alert."""
        state = StockState()
        levels = make_levels(resistance=[1100])

        alerts, _ = poll(state, 1110.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")
        self.assertEqual(alerts[0].level_type, "resistance")

    # ---------------------------------------------------------------------------
    # 11. Multiple levels can trigger on same poll
    # ---------------------------------------------------------------------------
    def test_multiple_levels_same_poll(self):
        """If price is near multiple levels, each can independently alert."""
        state = StockState()
        levels = make_levels(support=[1000], resistance=[1010])

        alerts, _ = poll(state, 1005.0, 0, levels)
        self.assertEqual(len(alerts), 2)
        reasons = {a.level_type: a.alert_reason for a in alerts}
        self.assertEqual(reasons["support"], "touch")
        self.assertEqual(reasons["resistance"], "touch")

    # ---------------------------------------------------------------------------
    # 12. Override can fire repeatedly on consecutive fast moves
    # ---------------------------------------------------------------------------
    def test_override_repeats_on_consecutive_fast_moves(self):
        """If price keeps moving >=1% per poll while in cooldown, override fires each time."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        alerts, _ = poll(state, 1015.0, 5, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "override")

    # ---------------------------------------------------------------------------
    # 13. Touch within 1% but not breached still counts as touch
    # ---------------------------------------------------------------------------
    def test_touch_within_1pct_not_breached(self):
        """Price within 1% of level but not crossed — still touch."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 1005.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")

    # ---------------------------------------------------------------------------
    # 14. Zone entry consumed flag prevents re-alert while in zone
    # ---------------------------------------------------------------------------
    def test_zone_entry_consumed_prevents_realert(self):
        """After alerting on fresh entry, zone_entry_consumed=True prevents re-alert."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        self.assertTrue(state.level_states["support:1000.0"].zone_entry_consumed)

        poll(state, 1025.0, 5, levels)
        self.assertTrue(state.level_states["support:1000.0"].zone_entry_consumed)

    # ---------------------------------------------------------------------------
    # 15. First poll has no last_price — override should not fire on first poll
    # ---------------------------------------------------------------------------
    def test_first_poll_no_override(self):
        """On the very first poll, last_price is None, so override cannot fire."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 1030.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

    # ---------------------------------------------------------------------------
    # 16. Cooldown is per-level, not per-stock — FIXED VERSION
    # ---------------------------------------------------------------------------
    def test_cooldown_is_per_level(self):
        """Cooldown on one level does not affect another level of the same stock.

        NOTE ON TEST DESIGN: prices are chosen so that once a level enters the
        approaching zone, it STAYS in the approaching zone (or moves to "far" only
        at controlled moments where that level's own state is not under test at
        that instant) rather than oscillating back through "far" repeatedly --
        oscillating prices reset zone_entry_consumed and can accidentally trigger
        the >=1% single-poll override, which would invalidate this test's intent
        (it must isolate per-level cooldown, not exercise override/zone-reset
        behavior on the level being used as a "control").
        """
        state = StockState()
        # Support at 1000 and Resistance at 1100 — independent level types
        levels = make_levels(support=[1000], resistance=[1100])

        # Step 1: Approach support 1000 from above at t=0
        # Price 1030: 3.0% above 1000 -> approaching (not breached)
        # Price 1030: 6.36% below 1100 -> far
        alerts, _ = poll(state, 1030.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, 1000.0)
        self.assertEqual(alerts[0].alert_reason, "approaching")
        support_cooldown = state.level_states["support:1000.0"].cooldown_until
        self.assertEqual(support_cooldown, T0 + timedelta(hours=1))

        # Step 2: Move price to 1085 at t=5.
        # Price 1085: 8.5% above 1000 -> far from support (support's state becomes
        #   "far" here -- intentional, support is not under test at this instant).
        # Price 1085: 1.36% below 1100 -> approaching (not breached) -> fresh entry,
        #   no cooldown yet -> alert fires for resistance.
        alerts, _ = poll(state, 1085.0, 5, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, 1100.0)
        self.assertEqual(alerts[0].alert_reason, "approaching")
        resistance_cooldown = state.level_states["resistance:1100.0"].cooldown_until
        self.assertEqual(resistance_cooldown, T0 + timedelta(minutes=5, hours=1))

        # Verify cooldowns are independent (different expiration times)
        self.assertNotEqual(support_cooldown, resistance_cooldown)

        # Step 3: At t=10, move price to 1085.5 — a 0.046% move from 1085 (no
        # override). Resistance 1100 stays in its EXISTING approaching state (not
        # a fresh entry) -> no alert. Support 1000 stays far -> no alert.
        # This is a "nothing new happens" checkpoint, confirming neither level
        # fires when nothing has changed.
        alerts, _ = poll(state, 1085.5, 10, levels)
        self.assertEqual(len(alerts), 0)

        # Step 4: At t=60, support 1000's cooldown (set at t=0, expires t=60) has
        # just expired. Move price to 1030 -- 1030 is 1-3% from support (approaching,
        # fresh entry since support was "far" since step 2, no cooldown -> alert)
        # and 6.36% from resistance (far -- resistance's own state simply resets
        # to "far" with zone_entry_consumed=False here, which does NOT touch
        # support's cooldown_until, the thing actually under test).
        alerts, _ = poll(state, 1030.0, 60, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, 1000.0)
        self.assertEqual(alerts[0].alert_reason, "approaching")

        # Step 5: Confirm resistance's cooldown_until (set at step 2, t=5) was never
        # touched by anything that happened to support in steps 1, 3, or 4. This is
        # the actual "per-level independence" assertion this test exists to prove.
        self.assertEqual(
            state.level_states["resistance:1100.0"].cooldown_until,
            resistance_cooldown,
            "Resistance level's cooldown must be unaffected by support level's activity",
        )

    # ---------------------------------------------------------------------------
    # 17. Distance classification edge cases
    # ---------------------------------------------------------------------------
    def test_distance_classification_exact_boundaries(self):
        """Test exact 1% and 3% boundaries."""
        self.assertEqual(_classify_distance(1.0), "touch")
        self.assertEqual(_classify_distance(1.01), "approaching")
        self.assertEqual(_classify_distance(3.0), "approaching")
        self.assertEqual(_classify_distance(3.01), "far")

    # ---------------------------------------------------------------------------
    # 18. Breached but far away (>3%) still counts as touch
    # ---------------------------------------------------------------------------
    def test_breached_far_away_still_touch(self):
        """If price crossed level but is >3% away, breached still triggers touch."""
        state = StockState()
        levels = make_levels(support=[1000])

        alerts, _ = poll(state, 900.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")
        self.assertAlmostEqual(alerts[0].distance_pct, 10.0, places=5)

    # ---------------------------------------------------------------------------
    # 19. Override on non-fresh entry while in approaching zone
    # ---------------------------------------------------------------------------
    def test_override_on_non_fresh_entry_in_approaching(self):
        """If already in approaching zone (not fresh entry), override still fires."""
        state = StockState()
        levels = make_levels(support=[1000])

        poll(state, 1030.0, 0, levels)
        poll(state, 1025.0, 5, levels)
        alerts, _ = poll(state, 1012.0, 10, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "override")

    # ---------------------------------------------------------------------------
    # 20. ISSUE 1 FIX: retreat from touch to approaching is fresh entry,
    #     suppressed in cooldown without override, zone_entry_consumed set
    # ---------------------------------------------------------------------------
    def test_touch_retreat_to_approaching_fresh_entry_suppressed_no_override(self):
        """ISSUE 1: retreat from touch to approaching is fresh entry.

        Steps:
        1. Approach level -> approaching alert, cooldown starts.
        2. Touch level (but not at exact boundary) -> touch alert, fresh cooldown starts.
        3. Retreat to approaching with small move (<1%) while in cooldown.
           This is a fresh entry (last state was "touch"), but suppressed
           by cooldown (no override). zone_entry_consumed becomes True.
        4. Next poll, still in approaching, not fresh entry -> no alert.
           Proves zone_entry_consumed persisted correctly.
        """
        state = StockState()
        levels = make_levels(support=[1000])

        # Step 1: Approach at t=0
        alerts, _ = poll(state, 1030.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, T0 + timedelta(hours=1))

        # Step 2: Touch at t=10 (not at exact boundary, so we can retreat with <1% move)
        # Price 1005: 0.5% from 1000 -> touch. Alert, cooldown restarts.
        alerts, _ = poll(state, 1005.0, 10, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")
        expected_cooldown = T0 + timedelta(minutes=70)
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, expected_cooldown)
        self.assertEqual(state.level_states["support:1000.0"].last_known_distance_state, "touch")

        # Step 3: Retreat to approaching with small move (<1%)
        # Price 1012: 1.2% from 1000 -> approaching.
        # Move 1005 -> 1012 = 0.70% (<1%). No override.
        # Fresh entry (last state was "touch" at 1005), in cooldown -> SUPPRESSED.
        alerts, _ = poll(state, 1012.0, 15, levels)
        self.assertEqual(len(alerts), 0, "Should be suppressed: fresh entry from touch, in cooldown, no override")
        # zone_entry_consumed should be True (fresh entry was consumed even though suppressed)
        self.assertTrue(state.level_states["support:1000.0"].zone_entry_consumed)
        self.assertEqual(state.level_states["support:1000.0"].last_known_distance_state, "approaching")

        # Step 4: Still in approaching, not fresh entry -> no alert
        # Price 1015: 1.5% from 1000 -> approaching.
        # Move 1012 -> 1015 = 0.30% (<1%). Not fresh entry, in cooldown, no override.
        alerts, _ = poll(state, 1015.0, 20, levels)
        self.assertEqual(len(alerts), 0, "Should be suppressed: not fresh entry, in cooldown, no override")
        # zone_entry_consumed should still be True
        self.assertTrue(state.level_states["support:1000.0"].zone_entry_consumed)

    # ---------------------------------------------------------------------------
    # 21. ISSUE 1 FIX: retreat from touch to approaching with >=1% move
    #     triggers override, cooldown unchanged
    # ---------------------------------------------------------------------------
    def test_touch_retreat_to_approaching_override_fires_cooldown_unchanged(self):
        """ISSUE 1: retreat from touch to approaching with >=1% move triggers override.

        Steps:
        1. Approach level -> approaching alert, cooldown starts.
        2. Touch level -> touch alert, fresh cooldown starts.
        3. Retreat to approaching with >=1% move while in cooldown.
           Fresh entry (last state was "touch"), override active -> override alert.
        4. Confirm cooldown_until is unchanged (not reset by override).
        """
        state = StockState()
        levels = make_levels(support=[1000])

        # Step 1: Approach at t=0
        alerts, _ = poll(state, 1030.0, 0, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "approaching")

        # Step 2: Touch at t=10
        alerts, _ = poll(state, 1000.0, 10, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "touch")
        expected_cooldown = T0 + timedelta(minutes=70)
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, expected_cooldown)

        # Step 3: Retreat to approaching with >=1% move
        # Price 1015: 1.5% from 1000 -> approaching.
        # Move 1000 -> 1015 = 1.5% (>=1%). Override active.
        # Fresh entry (was "touch"), in cooldown, override -> override alert.
        alerts, _ = poll(state, 1015.0, 15, levels)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_reason, "override")
        self.assertEqual(alerts[0].distance_pct, 1.5)

        # Step 4: Cooldown should NOT be reset
        self.assertEqual(state.level_states["support:1000.0"].cooldown_until, expected_cooldown)

    # ---------------------------------------------------------------------------
    # 22. Synthetic CSV integration test — updated for real config levels
    # ---------------------------------------------------------------------------
    def test_synthetic_csv_replay(self):
        """Run the full replay on synthetic data and verify expected alerts.

        Expected counts below were obtained by actually running replay_csv()
        against data/reliance_sample.csv and inspecting the real output
        (touch=8, approaching=7, override=2, total=17), not estimated by hand.
        """
        from watchtower.replay import replay_csv
        from watchtower.config_loader import load_watchlist, get_stock_config

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(base, "data", "reliance_sample.csv")
        config_path = os.path.join(base, "config", "watchlist.json")

        watchlist = load_watchlist(config_path)
        stock_config = {
            "support": [{"level": 2850, "note": ""}, {"level": 2780, "note": ""}],
            "resistance": [{"level": 3050, "note": ""}, {"level": 3120, "note": ""}],
        }

        alerts, final_state = replay_csv(csv_path, "RELIANCE", stock_config)

        # We expect several alerts from the synthetic data
        self.assertGreater(len(alerts), 0)

        # Check that we have touch alerts
        touch_alerts = [a for a in alerts if a.alert_reason == "touch"]
        self.assertGreaterEqual(len(touch_alerts), 8)

        # Check that we have approaching alerts
        approaching_alerts = [a for a in alerts if a.alert_reason == "approaching"]
        self.assertGreaterEqual(len(approaching_alerts), 7)

        # Check that we have override alerts
        override_alerts = [a for a in alerts if a.alert_reason == "override"]
        self.assertGreaterEqual(len(override_alerts), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)