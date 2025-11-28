"""
State generator - produces point values over time according to configured functions.
"""
import time
import math
import random
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .runtime_state import QualityCode


class FaultProfile:
    """Base class for fault profiles."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.start_time: Optional[float] = None

    def initialize(self, start_time: float) -> None:
        """Initialize fault profile."""
        self.start_time = start_time

    def apply(self, value: float | bool | int, quality: QualityCode, now: float) -> tuple[float | bool | int, QualityCode]:
        """
        Apply fault to value and quality.

        Returns:
            (modified_value, modified_quality)
        """
        return value, quality


class FreezeValueFault(FaultProfile):
    """Freeze value - quality becomes STALE, value doesn't change."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.frozen_value: Optional[float | bool | int] = None
        self.freeze_start: Optional[float] = None
        self.freeze_duration = config.get("duration_s", 10.0)
        self.freeze_interval = config.get("interval_s", 60.0)

    def apply(self, value: float | bool | int, quality: QualityCode, now: float) -> tuple[float | bool | int, QualityCode]:
        """Apply freeze fault."""
        if self.start_time is None:
            return value, quality

        elapsed = now - self.start_time

        # Determine if we should be frozen
        cycle_position = elapsed % self.freeze_interval
        should_freeze = cycle_position < self.freeze_duration

        if should_freeze:
            if self.frozen_value is None:
                self.frozen_value = value
            return self.frozen_value, QualityCode.STALE
        else:
            self.frozen_value = None
            return value, quality


class BadQualityBurstFault(FaultProfile):
    """Randomly set quality to BAD for short bursts."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.burst_probability = config.get("probability", 0.1)
        self.burst_duration = config.get("duration_s", 3.0)
        self.in_burst = False
        self.burst_start: Optional[float] = None

    def apply(self, value: float | bool | int, quality: QualityCode, now: float) -> tuple[float | bool | int, QualityCode]:
        """Apply bad quality burst fault."""
        if self.in_burst:
            # Check if burst should end
            if now - self.burst_start >= self.burst_duration:
                self.in_burst = False
            else:
                return value, QualityCode.BAD
        else:
            # Randomly start a burst
            if random.random() < self.burst_probability:
                self.in_burst = True
                self.burst_start = now
                return value, QualityCode.BAD

        return value, quality


class OutOfRangeSpikeFault(FaultProfile):
    """Occasional huge spike beyond eng_min/max."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.spike_probability = config.get("probability", 0.05)
        self.spike_multiplier = config.get("multiplier", 2.0)
        self.eng_min = config.get("eng_min", 0.0)
        self.eng_max = config.get("eng_max", 100.0)

    def apply(self, value: float | bool | int, quality: QualityCode, now: float) -> tuple[float | bool | int, QualityCode]:
        """Apply out-of-range spike fault."""
        # Only apply to numeric values
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return value, quality

        if random.random() < self.spike_probability:
            # Generate spike beyond range
            if random.random() < 0.5:
                # Spike below minimum
                spike_value = self.eng_min - (self.eng_max - self.eng_min) * (self.spike_multiplier - 1.0)
            else:
                # Spike above maximum
                spike_value = self.eng_max + (self.eng_max - self.eng_min) * (self.spike_multiplier - 1.0)

            return spike_value, QualityCode.UNCERTAIN

        return value, quality


# Fault profile registry
FAULT_PROFILES = {
    "freeze_value": FreezeValueFault,
    "bad_quality_bursts": BadQualityBurstFault,
    "out_of_range_spike": OutOfRangeSpikeFault,
}


@dataclass
class Sample:
    """A single point sample."""
    point_id: str
    value: float | bool | int
    quality: QualityCode
    timestamp: float


class GeneratorState:
    """Internal state for a single point generator."""

    def __init__(self, point_def: Dict[str, Any]):
        self.point_def = point_def
        self.point_id = point_def["point_id"]
        self.generator_config = point_def.get("generator", {})
        self.mode = self.generator_config.get("mode", "constant")
        self.params = self.generator_config.get("params", {})

        # Internal state
        self.start_time: Optional[float] = None
        self.last_value: Optional[float | bool | int] = None
        self.phase: float = 0.0  # For sine waves
        self.direction: int = 1  # For ramps
        self.digital_state: int = 0  # For digital points
        self.last_flip_time: float = 0.0

        # Fault profile
        self.fault_profile: Optional[FaultProfile] = None
        fault_config = self.generator_config.get("fault_profile")
        if fault_config:
            fault_type = fault_config.get("type")
            if fault_type in FAULT_PROFILES:
                fault_params = fault_config.get("params", {})
                # Add scale info if available for out_of_range_spike
                if fault_type == "out_of_range_spike" and "scale" in point_def:
                    scale = point_def["scale"]
                    fault_params.setdefault("eng_min", scale.get("eng_min", 0))
                    fault_params.setdefault("eng_max", scale.get("eng_max", 100))
                self.fault_profile = FAULT_PROFILES[fault_type](fault_params)

    def initialize(self, start_time: float) -> None:
        """Initialize generator state."""
        self.start_time = start_time

        # Initialize starting values based on mode
        if self.mode == "constant":
            self.last_value = self.params.get("value", 0.0)
        elif self.mode == "ramp":
            self.last_value = self.params.get("min", 0.0)
        elif self.mode == "sine":
            mid = (self.params.get("min", 0) + self.params.get("max", 100)) / 2
            self.last_value = mid
        elif self.mode == "random_walk":
            mid = (self.params.get("min", 0) + self.params.get("max", 100)) / 2
            self.last_value = mid
        elif self.mode == "step":
            self.last_value = self.params.get("initial_value", 0.0)
        elif self.mode == "digital_flip":
            self.digital_state = self.params.get("initial_state", 0)
            self.last_value = self.digital_state
            self.last_flip_time = start_time

        # Initialize fault profile
        if self.fault_profile:
            self.fault_profile.initialize(start_time)

    def generate(self, now: float) -> Sample:
        """Generate next sample."""
        if self.start_time is None:
            self.initialize(now)

        dt = now - self.start_time

        # Generate value based on mode
        if self.mode == "constant":
            value = self._generate_constant()
        elif self.mode == "ramp":
            value = self._generate_ramp(dt)
        elif self.mode == "sine":
            value = self._generate_sine(dt)
        elif self.mode == "random_walk":
            value = self._generate_random_walk(dt, now)
        elif self.mode == "step":
            value = self._generate_step(dt)
        elif self.mode == "digital_flip":
            value = self._generate_digital_flip(now)
        else:
            # Fallback for unknown modes
            value = 0.0

        self.last_value = value

        # Default quality is GOOD
        quality = QualityCode.GOOD

        # Apply fault profile if configured
        if self.fault_profile:
            value, quality = self.fault_profile.apply(value, quality, now)

        return Sample(
            point_id=self.point_id,
            value=value,
            quality=quality,
            timestamp=now
        )

    def _generate_constant(self) -> float:
        """Generate constant value."""
        return self.params.get("value", 0.0)

    def _generate_ramp(self, dt: float) -> float:
        """Generate ramping value between min and max."""
        min_val = self.params.get("min", 0.0)
        max_val = self.params.get("max", 100.0)
        period = self.params.get("period_s", 60.0)

        # Calculate position in cycle (0 to 1)
        cycle_position = (dt % period) / period

        # Linear ramp from min to max
        value = min_val + (max_val - min_val) * cycle_position

        return value

    def _generate_sine(self, dt: float) -> float:
        """Generate sinusoidal value."""
        min_val = self.params.get("min", 0.0)
        max_val = self.params.get("max", 100.0)
        period = self.params.get("period_s", 60.0)

        # Sine wave oscillating between min and max
        amplitude = (max_val - min_val) / 2
        offset = (max_val + min_val) / 2
        freq = 2 * math.pi / period

        value = offset + amplitude * math.sin(freq * dt)

        return value

    def _generate_random_walk(self, dt: float, now: float) -> float:
        """Generate random walk value."""
        min_val = self.params.get("min", 0.0)
        max_val = self.params.get("max", 100.0)
        step_size = self.params.get("step_size", 1.0)

        # Random step up or down
        step = random.uniform(-step_size, step_size)
        value = self.last_value + step

        # Clamp to bounds
        value = max(min_val, min(max_val, value))

        return value

    def _generate_step(self, dt: float) -> float:
        """Generate stepped value that changes at intervals."""
        step_interval = self.params.get("step_interval_s", 30.0)
        step_values = self.params.get("step_values", [0.0, 50.0, 100.0])

        # Determine which step we're on
        step_index = int(dt / step_interval) % len(step_values)
        value = step_values[step_index]

        return value

    def _generate_digital_flip(self, now: float) -> int:
        """Generate digital flip value (0/1 toggle)."""
        interval = self.params.get("interval_s", 60.0)

        # Check if it's time to flip
        if now - self.last_flip_time >= interval:
            self.digital_state = 1 - self.digital_state
            self.last_flip_time = now

        return self.digital_state


class StateGenerator:
    """Manages state generation for all points."""

    def __init__(self, point_definitions: List[Dict[str, Any]]):
        self.generators: Dict[str, GeneratorState] = {}

        # Create generator state for each scan-enabled point
        for point_def in point_definitions:
            if point_def.get("flags", {}).get("scan_enabled", False):
                point_id = point_def["point_id"]
                self.generators[point_id] = GeneratorState(point_def)

    def tick(self, now: float) -> List[Sample]:
        """Generate samples for all points at current time."""
        samples = []

        for generator in self.generators.values():
            sample = generator.generate(now)
            samples.append(sample)

        return samples

    def get_active_point_count(self) -> int:
        """Get count of active (scan-enabled) points."""
        return len(self.generators)
