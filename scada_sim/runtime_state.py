"""
Runtime state classes for SCADA points.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class QualityCode(Enum):
    """Quality codes for point values."""
    GOOD = "GOOD"
    BAD = "BAD"
    UNCERTAIN = "UNCERTAIN"
    STALE = "STALE"
    SIMULATED = "SIMULATED"


@dataclass
class AlarmState:
    """Alarm state for a point."""
    hi_hi_active: bool = False
    hi_active: bool = False
    lo_active: bool = False
    lo_lo_active: bool = False
    roc_active: bool = False

    def is_any_active(self) -> bool:
        """Check if any alarm is active."""
        return (self.hi_hi_active or self.hi_active or
                self.lo_active or self.lo_lo_active or self.roc_active)

    def get_highest_severity(self) -> Optional[str]:
        """Get the highest active alarm severity."""
        if self.hi_hi_active:
            return "HI_HI"
        if self.lo_lo_active:
            return "LO_LO"
        if self.hi_active:
            return "HI"
        if self.lo_active:
            return "LO"
        if self.roc_active:
            return "ROC"
        return None


@dataclass
class PointRuntimeState:
    """Runtime state for a single SCADA point."""
    point_id: str
    last_value: Optional[float | bool | int] = None
    last_quality: QualityCode = QualityCode.GOOD
    last_timestamp: Optional[float] = None
    last_roc: Optional[float] = None  # Rate of change for analogs
    alarm_state: AlarmState = None

    def __post_init__(self):
        if self.alarm_state is None:
            self.alarm_state = AlarmState()
