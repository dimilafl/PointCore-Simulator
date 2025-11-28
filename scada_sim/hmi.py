"""
HMI web interface - Flask-based minimal SCADA HMI.
"""
import time
import threading
from flask import Flask, jsonify, send_from_directory
from pathlib import Path

from .point_definitions import PointDefinitionEngine
from .state_generator import StateGenerator
from .alarm_evaluator import AlarmEvaluator
from .historian_logger import HistorianLogger


class HMIServer:
    """HMI server that runs simulation and serves web interface."""

    def __init__(self, engine: PointDefinitionEngine, tick_interval: float = 1.0):
        self.engine = engine
        self.tick_interval = tick_interval

        # Create simulator components
        self.generator = StateGenerator(engine.all_points())
        self.alarm_evaluator = AlarmEvaluator(engine.all_points())
        self.historian = HistorianLogger(engine.all_points())

        # Simulation state
        self.running = False
        self.sim_thread = None
        self.start_time = None

        # Flask app
        self.app = Flask(__name__, static_folder='../static')
        self._setup_routes()

    def _setup_routes(self):
        """Setup Flask routes."""

        @self.app.route('/')
        def index():
            """Serve main HMI page."""
            return send_from_directory(self.app.static_folder, 'index.html')

        @self.app.route('/api/points')
        def api_points():
            """Get current state of all points."""
            now = time.time()
            points_data = []

            for point_def in self.engine.all_points():
                point_id = point_def["point_id"]

                # Get current value from historian
                current_sample = self.historian.get_current_value(point_id)

                # Get alarm state
                alarm_state = self.alarm_evaluator.get_alarm_state(point_id)

                point_data = {
                    "point_id": point_id,
                    "name": point_def["name"],
                    "type": point_def["type"],
                    "eu": point_def.get("eu", ""),
                    "scan_enabled": point_def.get("flags", {}).get("scan_enabled", False),
                    "alarm_enabled": point_def.get("flags", {}).get("alarm_enabled", False)
                }

                if current_sample:
                    point_data["value"] = current_sample.value
                    point_data["quality"] = current_sample.quality
                    point_data["timestamp"] = current_sample.timestamp
                else:
                    point_data["value"] = None
                    point_data["quality"] = "N/A"
                    point_data["timestamp"] = None

                if alarm_state:
                    point_data["alarm_active"] = alarm_state.is_any_active()
                    point_data["alarm_severity"] = alarm_state.get_highest_severity()
                else:
                    point_data["alarm_active"] = False
                    point_data["alarm_severity"] = None

                # Add digital state labels if applicable
                if point_def["type"] == "digital":
                    digital_states = point_def.get("digital_states", {})
                    point_data["state_labels"] = {
                        "0": digital_states.get("0_label", "OFF"),
                        "1": digital_states.get("1_label", "ON")
                    }

                points_data.append(point_data)

            return jsonify({
                "points": points_data,
                "timestamp": now,
                "running": self.running
            })

        @self.app.route('/api/trend/<point_id>')
        def api_trend(point_id):
            """Get trend data for a specific point."""
            window_s = 300  # Last 5 minutes
            now = time.time()

            # Get recent samples
            samples = self.historian.get_recent_values(point_id, window_s, now)

            # Get recent events for this point
            events = self.historian.get_recent_events(window_s, now)
            point_events = [e for e in events if e.point_id == point_id]

            # Get point definition
            point_def = self.engine.get_point_def(point_id)

            trend_data = {
                "point_id": point_id,
                "name": point_def["name"] if point_def else point_id,
                "eu": point_def.get("eu", "") if point_def else "",
                "samples": [
                    {
                        "timestamp": s.timestamp,
                        "value": s.value,
                        "quality": s.quality
                    }
                    for s in samples
                ],
                "events": [
                    {
                        "timestamp": e.timestamp,
                        "severity": e.severity.name,
                        "state": e.state,
                        "message": e.message
                    }
                    for e in point_events
                ]
            }

            # Add alarm thresholds if analog
            if point_def and point_def["type"] == "analog" and "alarm" in point_def:
                alarm_cfg = point_def["alarm"]
                trend_data["thresholds"] = {
                    k: v for k, v in alarm_cfg.items()
                    if k in ["hi_hi", "hi", "lo", "lo_lo"]
                }

            return jsonify(trend_data)

        @self.app.route('/api/statistics')
        def api_statistics():
            """Get historian statistics."""
            stats = self.historian.get_statistics()
            return jsonify(stats)

    def _simulation_loop(self):
        """Background simulation loop."""
        self.start_time = time.time()

        while self.running:
            # Generate samples
            now = time.time()
            samples = self.generator.tick(now)

            # Evaluate alarms
            alarm_states, alarm_events = self.alarm_evaluator.evaluate(samples)

            # Record to historian
            self.historian.record(samples, alarm_events)

            # Sleep until next tick
            time.sleep(self.tick_interval)

    def start_simulation(self):
        """Start the simulation loop in background."""
        if not self.running:
            self.running = True
            self.sim_thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.sim_thread.start()

    def stop_simulation(self):
        """Stop the simulation loop."""
        self.running = False
        if self.sim_thread:
            self.sim_thread.join(timeout=5.0)

    def run(self, host='127.0.0.1', port=5000, debug=False):
        """Run the Flask server."""
        self.start_simulation()
        try:
            self.app.run(host=host, port=port, debug=debug, use_reloader=False)
        finally:
            self.stop_simulation()
