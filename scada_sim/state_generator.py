"""
State generator - produces point values over time according to configured functions.
"""
import time
import math
import random
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .runtime_state import QualityCode


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

        # Default quality is GOOD (will add fault profiles in Milestone 6)
        quality = QualityCode.GOOD

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
