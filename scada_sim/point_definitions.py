"""
Point definition engine - loads and validates point configurations.
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class PointDefinitionEngine:
    """Loads and manages SCADA point definitions."""

    VALID_TYPES = {"analog", "digital"}
    VALID_GENERATOR_MODES = {"ramp", "sine", "step", "random_walk", "constant", "digital_flip"}

    def __init__(self):
        self.points: Dict[str, Dict[str, Any]] = {}

    def load_from_file(self, filepath: str) -> None:
        """Load point definitions from JSON file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Point definition file not found: {filepath}")

        with open(path, 'r') as f:
            data = json.load(f)

        # Support both array format and dict format
        if isinstance(data, list):
            points_list = data
        elif isinstance(data, dict) and "points" in data:
            points_list = data["points"]
        else:
            raise ValueError("JSON must be an array or object with 'points' key")

        for point_def in points_list:
            self._validate_and_add(point_def)

    def _validate_and_add(self, point_def: Dict[str, Any]) -> None:
        """Validate and add a point definition."""
        # Required fields
        if "point_id" not in point_def:
            raise ValueError("Point definition missing required field: point_id")
        if "name" not in point_def:
            raise ValueError(f"Point {point_def['point_id']} missing required field: name")
        if "type" not in point_def:
            raise ValueError(f"Point {point_def['point_id']} missing required field: type")

        point_id = point_def["point_id"]

        # Check for duplicate IDs
        if point_id in self.points:
            raise ValueError(f"Duplicate point_id: {point_id}")

        # Validate type
        point_type = point_def["type"]
        if point_type not in self.VALID_TYPES:
            raise ValueError(f"Point {point_id} has invalid type '{point_type}'. Must be one of {self.VALID_TYPES}")

        # Validate generator if present
        if "generator" in point_def:
            generator = point_def["generator"]
            if "mode" not in generator:
                raise ValueError(f"Point {point_id} generator missing 'mode'")
            if generator["mode"] not in self.VALID_GENERATOR_MODES:
                raise ValueError(
                    f"Point {point_id} has invalid generator mode '{generator['mode']}'. "
                    f"Must be one of {self.VALID_GENERATOR_MODES}"
                )

        # Validate analog-specific fields
        if point_type == "analog":
            self._validate_analog_point(point_id, point_def)

        # Validate digital-specific fields
        if point_type == "digital":
            self._validate_digital_point(point_id, point_def)

        # Store the point
        self.points[point_id] = point_def

    def _validate_analog_point(self, point_id: str, point_def: Dict[str, Any]) -> None:
        """Validate analog-specific fields."""
        # Check alarm thresholds are in correct order if all present
        if "alarm" in point_def:
            alarm = point_def["alarm"]
            thresholds = []

            if "lo_lo" in alarm:
                thresholds.append(("lo_lo", alarm["lo_lo"]))
            if "lo" in alarm:
                thresholds.append(("lo", alarm["lo"]))
            if "hi" in alarm:
                thresholds.append(("hi", alarm["hi"]))
            if "hi_hi" in alarm:
                thresholds.append(("hi_hi", alarm["hi_hi"]))

            # Verify ordering: lo_lo < lo < hi < hi_hi
            values = [t[1] for t in thresholds]
            if values != sorted(values):
                raise ValueError(
                    f"Point {point_id} alarm thresholds not in correct order. "
                    f"Must be: lo_lo < lo < hi < hi_hi"
                )

    def _validate_digital_point(self, point_id: str, point_def: Dict[str, Any]) -> None:
        """Validate digital-specific fields."""
        # Digital points should have digital_states
        if "digital_states" in point_def:
            states = point_def["digital_states"]
            # Validate alarm_on_state if present
            if "alarm_on_state" in states:
                alarm_state = states["alarm_on_state"]
                if alarm_state not in [0, 1, None]:
                    raise ValueError(
                        f"Point {point_id} has invalid alarm_on_state '{alarm_state}'. "
                        f"Must be 0, 1, or null"
                    )

    def get_point_def(self, point_id: str) -> Optional[Dict[str, Any]]:
        """Get point definition by ID."""
        return self.points.get(point_id)

    def all_points(self) -> List[Dict[str, Any]]:
        """Get all point definitions."""
        return list(self.points.values())

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get a summary of loaded points."""
        analog_count = sum(1 for p in self.points.values() if p["type"] == "analog")
        digital_count = sum(1 for p in self.points.values() if p["type"] == "digital")
        scan_enabled = sum(1 for p in self.points.values()
                          if p.get("flags", {}).get("scan_enabled", False))
        alarm_enabled = sum(1 for p in self.points.values()
                           if p.get("flags", {}).get("alarm_enabled", False))

        return {
            "total_points": len(self.points),
            "analog_points": analog_count,
            "digital_points": digital_count,
            "scan_enabled": scan_enabled,
            "alarm_enabled": alarm_enabled,
            "point_ids": list(self.points.keys())
        }
