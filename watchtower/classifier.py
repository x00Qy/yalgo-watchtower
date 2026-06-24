"""YALGO Watchtower Phase 1 — Alert Decision Engine.

Rules Summary (priority order, first match wins per poll per level):
  1. TOUCH: distance_pct <= 1% OR price crossed level. ALWAYS fires,
     ignores cooldown. Starts/restarts a fresh 1-hour cooldown.
  2. APPROACHING: 1% < distance_pct <= 3%. Fires ONCE on fresh entry
     into the zone. Suppressed during cooldown unless overridden by Rule 3.
  3. OVERRIDE: If stock moved >= 1% in a single poll, bypass cooldown
     for APPROACHING alerts. Does NOT reset cooldown timer.
  4. COOLDOWN: 1-hour per (stock, level) after Rule 1 or Rule 2 fires.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass
class AlertEvent:
    stock: str
    level: float
    level_type: str
    distance_pct: float
    alert_reason: str        # "touch" | "approaching" | "override"
    current_price: float
    timestamp: datetime

    def __repr__(self) -> str:
        return (
            f"Alert({self.stock} {self.level_type}={self.level:.2f} "
            f"reason={self.alert_reason} price={self.current_price:.2f} "
            f"dist={self.distance_pct:.3f}% @ {self.timestamp.isoformat()})"
        )


@dataclass
class LevelState:
    last_known_distance_state: str = "far"
    cooldown_until: Optional[datetime] = None
    zone_entry_consumed: bool = False


@dataclass
class StockState:
    last_price: Optional[float] = None
    last_poll_time: Optional[datetime] = None
    level_states: Dict[str, LevelState] = field(default_factory=dict)


def _make_level_key(level_type: str, level: float) -> str:
    return f"{level_type}:{level}"


def _distance_pct(price: float, level: float) -> float:
    return abs(price - level) / level * 100.0


def _classify_distance(distance_pct: float) -> str:
    if distance_pct <= 1.0:
        return "touch"
    if distance_pct <= 3.0:
        return "approaching"
    return "far"


def _is_breached(price: float, level: float, level_type: str) -> bool:
    if level_type == "support":
        return price < level
    else:
        return price > level


def _single_poll_move_pct(current_price: float, last_price: float) -> float:
    if last_price is None or last_price == 0:
        return 0.0
    return abs(current_price - last_price) / last_price * 100.0


def evaluate_poll(
    stock_symbol: str,
    current_price: float,
    stock_state: StockState,
    levels_config: dict,
    current_time: datetime,
) -> List[AlertEvent]:
    alerts: List[AlertEvent] = []

    move_pct = _single_poll_move_pct(current_price, stock_state.last_price)
    override_active = move_pct >= 1.0

    for level_type in ("support", "resistance"):
        for level_obj in levels_config.get(level_type, []):
            level = float(level_obj["level"])
            key = _make_level_key(level_type, level)
            if key not in stock_state.level_states:
                stock_state.level_states[key] = LevelState()

    for level_type in ("support", "resistance"):
        for level_obj in levels_config.get(level_type, []):
            level = float(level_obj["level"])
            key = _make_level_key(level_type, level)
            state = stock_state.level_states[key]

            dist = _distance_pct(current_price, level)
            distance_class = _classify_distance(dist)
            breached = _is_breached(current_price, level, level_type)

            in_cooldown = (
                state.cooldown_until is not None
                and current_time < state.cooldown_until
            )

            # -----------------------------------------------------------------
            # A. TOUCH RULE (Rule 1) — ALWAYS fires, ignores cooldown.
            #    Restarts cooldown every time.
            # -----------------------------------------------------------------
            is_touch = (distance_class == "touch") or breached

            if is_touch:
                # Silence only if price has clearly broken ABOVE resistance (>2% past level)
                # Support breaks always fire — a support crash is always noteworthy
                clearly_broken = breached and dist > 2.0 and level_type == "resistance"
                if not clearly_broken:
                    alerts.append(AlertEvent(
                        stock=stock_symbol,
                        level=level,
                        level_type=level_type,
                        distance_pct=dist,
                        alert_reason="touch",
                        current_price=current_price,
                        timestamp=current_time,
                    ))
                    # Always restart cooldown on touch
                    state.cooldown_until = current_time + timedelta(hours=1)
                state.last_known_distance_state = "touch"
                continue

            # -----------------------------------------------------------------
            # B. APPROACHING ZONE (Rule 2) — suppressed during cooldown
            #    unless Rule 3 override active.
            # -----------------------------------------------------------------
            if distance_class == "approaching":
                fresh_entry = (state.last_known_distance_state in ("far", "touch"))

                should_alert = False
                alert_reason = None

                if fresh_entry:
                    if not in_cooldown:
                        should_alert = True
                        alert_reason = "approaching"
                    else:
                        if override_active:
                            should_alert = True
                            alert_reason = "override"
                    state.zone_entry_consumed = True
                else:
                    if override_active:
                        should_alert = True
                        alert_reason = "override"

                if should_alert:
                    alerts.append(AlertEvent(
                        stock=stock_symbol,
                        level=level,
                        level_type=level_type,
                        distance_pct=dist,
                        alert_reason=alert_reason,
                        current_price=current_price,
                        timestamp=current_time,
                    ))
                    if alert_reason == "approaching":
                        state.cooldown_until = current_time + timedelta(hours=1)

                state.last_known_distance_state = "approaching"
                continue

            # -----------------------------------------------------------------
            # C. FAR (> 3%) — reset flags, no alert.
            # -----------------------------------------------------------------
            if distance_class == "far":
                state.zone_entry_consumed = False
                state.last_known_distance_state = "far"
                continue

    stock_state.last_price = current_price
    stock_state.last_poll_time = current_time

    return alerts