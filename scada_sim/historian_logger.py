"""
Historian logger - records point values and events with deadband/compression.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import deque

from .state_generator import Sample
from .alarm_evaluator import AlarmEvent


@dataclass
class HistorianSample:
    """A recorded historian sample."""
    timestamp: float
    point_id: str
    value: float | bool | int
    quality: str


class PointHistorian:
    """Manages historian for a single point."""

    def __init__(self, point_def: Dict):
        self.point_id = point_def["point_id"]
        self.logging_config = point_def.get("logging", {})

        # Deadband and compression settings
        self.deadband = self.logging_config.get("deadband", 0.0)
        self.compression = self.logging_config.get("compression", False)
        self.max_rate_s = self.logging_config.get("max_rate_s", 1.0)

        # Last logged state
        self.last_logged_value: Optional[float | bool | int] = None
        self.last_logged_timestamp: Optional[float] = None

        # In-memory buffer (keep last 10000 samples)
        self.samples: deque[HistorianSample] = deque(maxlen=10000)

        # Statistics
        self.total_samples_received = 0
        self.total_samples_logged = 0

    def should_log(self, sample: Sample) -> bool:
        """Determine if sample should be logged."""
        # Always log first sample
        if self.last_logged_value is None:
            return True

        # Check max rate
        if self.last_logged_timestamp is not None:
            elapsed = sample.timestamp - self.last_logged_timestamp
            if elapsed < self.max_rate_s:
                return False

        # Check deadband (for numeric values)
        if isinstance(sample.value, (int, float)) and not isinstance(sample.value, bool):
            if self.compression and self.deadband > 0:
                delta = abs(float(sample.value) - float(self.last_logged_value))
                if delta < self.deadband:
                    return False

        # For digital values, only log on change
        if isinstance(sample.value, bool) or (isinstance(sample.value, int) and sample.value in [0, 1]):
            if sample.value == self.last_logged_value:
                return False

        return True

    def record(self, sample: Sample) -> bool:
        """
        Record a sample if it passes filtering.

        Returns:
            True if logged, False if filtered out
        """
        self.total_samples_received += 1

        if self.should_log(sample):
            historian_sample = HistorianSample(
                timestamp=sample.timestamp,
                point_id=sample.point_id,
                value=sample.value,
                quality=sample.quality.value
            )
            self.samples.append(historian_sample)

            self.last_logged_value = sample.value
            self.last_logged_timestamp = sample.timestamp
            self.total_samples_logged += 1
            return True

        return False

    def get_current_value(self) -> Optional[HistorianSample]:
        """Get the most recent logged sample."""
        if self.samples:
            return self.samples[-1]
        return None

    def get_recent_samples(self, window_s: float, now: float) -> List[HistorianSample]:
        """Get samples from the last window_s seconds."""
        cutoff = now - window_s
        return [s for s in self.samples if s.timestamp >= cutoff]

    def get_compression_ratio(self) -> float:
        """Get compression ratio (samples received / samples logged)."""
        if self.total_samples_logged == 0:
            return 0.0
        return self.total_samples_received / self.total_samples_logged


class HistorianLogger:
    """Manages historian logging for all points."""

    def __init__(self, point_definitions: List[Dict]):
        # Point historians
        self.historians: Dict[str, PointHistorian] = {}
        for point_def in point_definitions:
            point_id = point_def["point_id"]
            self.historians[point_id] = PointHistorian(point_def)

        # Event buffer (keep last 1000 events)
        self.events: deque[AlarmEvent] = deque(maxlen=1000)

        # Statistics
        self.total_events = 0

    def record(self, samples: List[Sample], events: List[AlarmEvent]) -> Dict[str, int]:
        """
        Record samples and events.

        Returns:
            Dict with counts: {"samples_logged": N, "samples_filtered": M, "events_logged": K}
        """
        samples_logged = 0
        samples_filtered = 0

        # Record samples
        for sample in samples:
            if sample.point_id in self.historians:
                historian = self.historians[sample.point_id]
                if historian.record(sample):
                    samples_logged += 1
                else:
                    samples_filtered += 1

        # Record events (all events are logged)
        for event in events:
            self.events.append(event)
            self.total_events += 1

        return {
            "samples_logged": samples_logged,
            "samples_filtered": samples_filtered,
            "events_logged": len(events)
        }

    def get_current_value(self, point_id: str) -> Optional[HistorianSample]:
        """Get current value for a point."""
        if point_id in self.historians:
            return self.historians[point_id].get_current_value()
        return None

    def get_recent_values(self, point_id: str, window_s: float, now: float) -> List[HistorianSample]:
        """Get recent values for a point within time window."""
        if point_id in self.historians:
            return self.historians[point_id].get_recent_samples(window_s, now)
        return []

    def get_recent_events(self, window_s: float, now: float) -> List[AlarmEvent]:
        """Get recent events within time window."""
        cutoff = now - window_s
        return [e for e in self.events if e.timestamp >= cutoff]

    def get_statistics(self) -> Dict[str, any]:
        """Get historian statistics."""
        stats = {
            "total_events": self.total_events,
            "points": {}
        }

        for point_id, historian in self.historians.items():
            stats["points"][point_id] = {
                "samples_received": historian.total_samples_received,
                "samples_logged": historian.total_samples_logged,
                "samples_filtered": historian.total_samples_received - historian.total_samples_logged,
                "compression_ratio": historian.get_compression_ratio(),
                "buffer_size": len(historian.samples)
            }

        return stats

    def print_statistics(self) -> None:
        """Print historian statistics to console."""
        stats = self.get_statistics()

        print("\n" + "=" * 100)
        print("HISTORIAN STATISTICS")
        print("=" * 100)
        print(f"Total Events: {stats['total_events']}")
        print("\nPer-Point Statistics:")
        print(f"{'Point ID':<12} {'Received':<12} {'Logged':<12} {'Filtered':<12} {'Compression':<15} {'Buffer':<10}")
        print("-" * 100)

        for point_id, point_stats in stats["points"].items():
            compression = f"{point_stats['compression_ratio']:.2f}x" if point_stats['compression_ratio'] > 0 else "N/A"
            print(
                f"{point_id:<12} "
                f"{point_stats['samples_received']:<12} "
                f"{point_stats['samples_logged']:<12} "
                f"{point_stats['samples_filtered']:<12} "
                f"{compression:<15} "
                f"{point_stats['buffer_size']:<10}"
            )

        print("=" * 100)
