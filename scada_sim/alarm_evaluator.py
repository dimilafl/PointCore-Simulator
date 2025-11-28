"""
Alarm evaluator - evaluates alarm conditions and manages state transitions.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import IntEnum

from .state_generator import Sample
from .runtime_state import AlarmState


class AlarmSeverity(IntEnum):
    """Alarm severity levels."""
    LO_LO = 1
    LO = 2
    HI = 3
    HI_HI = 4
    ROC = 5


@dataclass
class AlarmEvent:
    """Alarm event record."""
    timestamp: float
    point_id: str
    severity: AlarmSeverity
    state: str  # "ACTIVE" or "CLEAR"
    message: str


class AlarmTimer:
    """Manages delay timers for alarm state transitions."""

    def __init__(self, delay_on: float = 0.0, delay_off: float = 0.0):
        self.delay_on = delay_on
        self.delay_off = delay_off
        self.condition_start_time: Optional[float] = None
        self.alarm_active = False

    def evaluate(self, condition: bool, now: float) -> tuple[bool, bool]:
        """
        Evaluate condition with delays.

        Returns:
            (alarm_active, state_changed)
        """
        state_changed = False

        if condition:
            # Condition is true
            if self.condition_start_time is None:
                self.condition_start_time = now

            # Check if delay_on has elapsed
            if not self.alarm_active:
                elapsed = now - self.condition_start_time
                if elapsed >= self.delay_on:
                    self.alarm_active = True
                    state_changed = True
        else:
            # Condition is false
            if self.condition_start_time is not None:
                # Check if we need to clear the alarm
                if self.alarm_active:
                    # Already in alarm, check delay_off
                    elapsed = now - self.condition_start_time
                    if elapsed >= self.delay_off:
                        self.alarm_active = False
                        state_changed = True
                        self.condition_start_time = None
                else:
                    # Not in alarm yet, just reset timer
                    self.condition_start_time = None

        return self.alarm_active, state_changed


class PointAlarmEvaluator:
    """Evaluates alarms for a single point."""

    def __init__(self, point_def: Dict[str, Any]):
        self.point_def = point_def
        self.point_id = point_def["point_id"]
        self.point_type = point_def["type"]
        self.alarm_config = point_def.get("alarm", {})
        self.alarm_enabled = point_def.get("flags", {}).get("alarm_enabled", False)

        # Previous state for ROC calculation
        self.last_value: Optional[float] = None
        self.last_timestamp: Optional[float] = None

        # Alarm timers
        self.timers: Dict[str, AlarmTimer] = {}

        if self.alarm_enabled and self.point_type == "analog":
            delay_on = self.alarm_config.get("delay_on", 0.0)
            delay_off = self.alarm_config.get("delay_off", 0.0)

            if "hi_hi" in self.alarm_config:
                self.timers["hi_hi"] = AlarmTimer(delay_on, delay_off)
            if "hi" in self.alarm_config:
                self.timers["hi"] = AlarmTimer(delay_on, delay_off)
            if "lo" in self.alarm_config:
                self.timers["lo"] = AlarmTimer(delay_on, delay_off)
            if "lo_lo" in self.alarm_config:
                self.timers["lo_lo"] = AlarmTimer(delay_on, delay_off)
            if "roc_threshold" in self.alarm_config:
                self.timers["roc"] = AlarmTimer(delay_on, delay_off)

        # Current alarm state
        self.alarm_state = AlarmState()

    def evaluate(self, sample: Sample) -> tuple[AlarmState, List[AlarmEvent]]:
        """
        Evaluate alarms for the sample.

        Returns:
            (updated_alarm_state, alarm_events)
        """
        events = []

        if not self.alarm_enabled:
            return self.alarm_state, events

        if self.point_type == "analog":
            events = self._evaluate_analog(sample)
        elif self.point_type == "digital":
            events = self._evaluate_digital(sample)

        return self.alarm_state, events

    def _evaluate_analog(self, sample: Sample) -> List[AlarmEvent]:
        """Evaluate analog alarms."""
        events = []
        value = float(sample.value)
        now = sample.timestamp

        # Evaluate threshold alarms
        # HI_HI
        if "hi_hi" in self.timers:
            threshold = self.alarm_config["hi_hi"]
            condition = value >= threshold
            active, changed = self.timers["hi_hi"].evaluate(condition, now)

            if changed:
                self.alarm_state.hi_hi_active = active
                events.append(AlarmEvent(
                    timestamp=now,
                    point_id=self.point_id,
                    severity=AlarmSeverity.HI_HI,
                    state="ACTIVE" if active else "CLEAR",
                    message=f"HI_HI alarm {value:.2f} >= {threshold}" if active else f"HI_HI cleared {value:.2f}"
                ))

        # HI
        if "hi" in self.timers:
            threshold = self.alarm_config["hi"]
            condition = value >= threshold
            active, changed = self.timers["hi"].evaluate(condition, now)

            if changed:
                self.alarm_state.hi_active = active
                events.append(AlarmEvent(
                    timestamp=now,
                    point_id=self.point_id,
                    severity=AlarmSeverity.HI,
                    state="ACTIVE" if active else "CLEAR",
                    message=f"HI alarm {value:.2f} >= {threshold}" if active else f"HI cleared {value:.2f}"
                ))

        # LO
        if "lo" in self.timers:
            threshold = self.alarm_config["lo"]
            condition = value <= threshold
            active, changed = self.timers["lo"].evaluate(condition, now)

            if changed:
                self.alarm_state.lo_active = active
                events.append(AlarmEvent(
                    timestamp=now,
                    point_id=self.point_id,
                    severity=AlarmSeverity.LO,
                    state="ACTIVE" if active else "CLEAR",
                    message=f"LO alarm {value:.2f} <= {threshold}" if active else f"LO cleared {value:.2f}"
                ))

        # LO_LO
        if "lo_lo" in self.timers:
            threshold = self.alarm_config["lo_lo"]
            condition = value <= threshold
            active, changed = self.timers["lo_lo"].evaluate(condition, now)

            if changed:
                self.alarm_state.lo_lo_active = active
                events.append(AlarmEvent(
                    timestamp=now,
                    point_id=self.point_id,
                    severity=AlarmSeverity.LO_LO,
                    state="ACTIVE" if active else "CLEAR",
                    message=f"LO_LO alarm {value:.2f} <= {threshold}" if active else f"LO_LO cleared {value:.2f}"
                ))

        # ROC (Rate of Change)
        if "roc" in self.timers and self.last_value is not None and self.last_timestamp is not None:
            dt = now - self.last_timestamp
            if dt > 0:
                roc = abs(value - self.last_value) / dt
                roc_threshold = self.alarm_config["roc_threshold"]
                condition = roc > roc_threshold

                active, changed = self.timers["roc"].evaluate(condition, now)

                if changed:
                    self.alarm_state.roc_active = active
                    events.append(AlarmEvent(
                        timestamp=now,
                        point_id=self.point_id,
                        severity=AlarmSeverity.ROC,
                        state="ACTIVE" if active else "CLEAR",
                        message=f"ROC alarm {roc:.2f}/s > {roc_threshold}" if active else f"ROC cleared {roc:.2f}/s"
                    ))

        # Update history for ROC
        self.last_value = value
        self.last_timestamp = now

        return events

    def _evaluate_digital(self, sample: Sample) -> List[AlarmEvent]:
        """Evaluate digital alarms."""
        events = []

        digital_states = self.point_def.get("digital_states", {})
        alarm_on_state = digital_states.get("alarm_on_state")

        if alarm_on_state is not None:
            current_state = int(sample.value)
            should_alarm = (current_state == alarm_on_state)

            # Digital alarms have no delay - immediate
            # We'll use hi_active to track digital alarm state
            if should_alarm != self.alarm_state.hi_active:
                self.alarm_state.hi_active = should_alarm
                events.append(AlarmEvent(
                    timestamp=sample.timestamp,
                    point_id=self.point_id,
                    severity=AlarmSeverity.HI,
                    state="ACTIVE" if should_alarm else "CLEAR",
                    message=f"Digital alarm state={current_state}" if should_alarm else f"Digital cleared state={current_state}"
                ))

        return events


class AlarmEvaluator:
    """Manages alarm evaluation for all points."""

    def __init__(self, point_definitions: List[Dict[str, Any]]):
        self.evaluators: Dict[str, PointAlarmEvaluator] = {}

        # Create evaluator for each alarm-enabled point
        for point_def in point_definitions:
            if point_def.get("flags", {}).get("alarm_enabled", False):
                point_id = point_def["point_id"]
                self.evaluators[point_id] = PointAlarmEvaluator(point_def)

    def evaluate(self, samples: List[Sample]) -> tuple[Dict[str, AlarmState], List[AlarmEvent]]:
        """
        Evaluate alarms for all samples.

        Returns:
            (alarm_states_dict, all_alarm_events)
        """
        all_events = []
        alarm_states = {}

        for sample in samples:
            if sample.point_id in self.evaluators:
                evaluator = self.evaluators[sample.point_id]
                alarm_state, events = evaluator.evaluate(sample)
                alarm_states[sample.point_id] = alarm_state
                all_events.extend(events)

        return alarm_states, all_events

    def get_alarm_state(self, point_id: str) -> Optional[AlarmState]:
        """Get current alarm state for a point."""
        if point_id in self.evaluators:
            return self.evaluators[point_id].alarm_state
        return None
