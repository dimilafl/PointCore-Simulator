#!/usr/bin/env python3
"""
PointCore-Simulator CLI entry point.
"""
import argparse
import sys
import time
from datetime import datetime

from scada_sim.point_definitions import PointDefinitionEngine
from scada_sim.runtime_state import PointRuntimeState, QualityCode
from scada_sim.state_generator import StateGenerator
from scada_sim.alarm_evaluator import AlarmEvaluator
from scada_sim.historian_logger import HistorianLogger
from scada_sim.hmi import HMIServer


def load_and_validate(config_file: str, quiet: bool = False) -> PointDefinitionEngine:
    """Load point definitions and validate."""
    engine = PointDefinitionEngine()

    try:
        if not quiet:
            print(f"Loading point definitions from: {config_file}")
        engine.load_from_file(config_file)
        if not quiet:
            print("✓ Point definitions loaded successfully\n")
    except FileNotFoundError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"✗ Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

    return engine


def print_validation_summary(engine: PointDefinitionEngine) -> None:
    """Print validation summary."""
    summary = engine.get_validation_summary()

    print("=" * 60)
    print("POINT DEFINITION VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total Points:      {summary['total_points']}")
    print(f"  Analog:          {summary['analog_points']}")
    print(f"  Digital:         {summary['digital_points']}")
    print(f"Scan Enabled:      {summary['scan_enabled']}")
    print(f"Alarm Enabled:     {summary['alarm_enabled']}")
    print("=" * 60)


def print_point_details(engine: PointDefinitionEngine) -> None:
    """Print detailed information for each point."""
    print("\nPOINT DETAILS")
    print("=" * 60)

    for point_def in engine.all_points():
        point_id = point_def["point_id"]
        name = point_def["name"]
        point_type = point_def["type"]
        flags = point_def.get("flags", {})

        print(f"\n[{point_id}] {name}")
        print(f"  Type: {point_type.upper()}")

        if point_type == "analog":
            eu = point_def.get("eu", "units")
            scale = point_def.get("scale", {})
            print(f"  EU: {eu}")
            if scale:
                print(f"  Range: {scale.get('eng_min', 0)} - {scale.get('eng_max', 100)} {eu}")

        if point_type == "digital":
            states = point_def.get("digital_states", {})
            print(f"  States: 0={states.get('0_label', 'OFF')}, 1={states.get('1_label', 'ON')}")

        # Generator info
        if "generator" in point_def:
            gen = point_def["generator"]
            mode = gen.get("mode", "unknown")
            print(f"  Generator: {mode.upper()}")

        # Flags
        scan = "YES" if flags.get("scan_enabled", False) else "NO"
        alarm = "YES" if flags.get("alarm_enabled", False) else "NO"
        print(f"  Scan: {scan} | Alarm: {alarm}")

        # Alarm thresholds for analog
        if point_type == "analog" and "alarm" in point_def:
            alarm_cfg = point_def["alarm"]
            thresholds = []
            if "hi_hi" in alarm_cfg:
                thresholds.append(f"HI_HI={alarm_cfg['hi_hi']}")
            if "hi" in alarm_cfg:
                thresholds.append(f"HI={alarm_cfg['hi']}")
            if "lo" in alarm_cfg:
                thresholds.append(f"LO={alarm_cfg['lo']}")
            if "lo_lo" in alarm_cfg:
                thresholds.append(f"LO_LO={alarm_cfg['lo_lo']}")
            if "roc_threshold" in alarm_cfg:
                thresholds.append(f"ROC={alarm_cfg['roc_threshold']}")

            if thresholds:
                print(f"  Alarms: {', '.join(thresholds)}")

    print("\n" + "=" * 60)


def initialize_runtime_state(engine: PointDefinitionEngine) -> dict:
    """Initialize runtime state for all points."""
    runtime_states = {}

    for point_def in engine.all_points():
        point_id = point_def["point_id"]
        runtime_states[point_id] = PointRuntimeState(
            point_id=point_id,
            last_quality=QualityCode.SIMULATED  # Start as simulated
        )

    return runtime_states


def cmd_validate(args):
    """Validate command - load and validate point definitions."""
    # Load and validate
    engine = load_and_validate(args.config)

    # Print summary
    print_validation_summary(engine)

    # Print details if requested
    if args.detailed:
        print_point_details(engine)

    # Initialize runtime state
    runtime_states = initialize_runtime_state(engine)
    print(f"\n✓ Initialized runtime state for {len(runtime_states)} points")

    print("\n✓ Milestone 1 complete: Point definitions loaded and validated")


def cmd_run(args):
    """Run command - start the simulation loop."""
    # Load point definitions
    engine = load_and_validate(args.config, quiet=True)

    # Create state generator, alarm evaluator, and historian
    generator = StateGenerator(engine.all_points())
    alarm_evaluator = AlarmEvaluator(engine.all_points())
    historian = HistorianLogger(engine.all_points())
    active_count = generator.get_active_point_count()

    print("=" * 100)
    print("POINTCORE SIMULATOR - RUNNING")
    print("=" * 100)
    print(f"Active points: {active_count}")
    print(f"Tick interval: {args.interval}s")
    print(f"Total ticks: {args.ticks if args.ticks > 0 else 'unlimited'}")
    print("=" * 100)
    print(f"{'Tick':<6} {'Timestamp':<20} {'Point ID':<12} {'Value':<15} {'Quality':<12} {'Alarm':<20}")
    print("-" * 100)

    start_time = time.time()
    tick_count = 0
    total_alarm_events = 0

    try:
        while True:
            # Check tick limit
            if args.ticks > 0 and tick_count >= args.ticks:
                break

            # Generate samples
            now = time.time()
            samples = generator.tick(now)

            # Evaluate alarms
            alarm_states, alarm_events = alarm_evaluator.evaluate(samples)

            # Record to historian
            historian.record(samples, alarm_events)

            # Print alarm events if any
            for event in alarm_events:
                timestamp_str = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S.%f")[:-3]
                print(f"{'[ALM]':<6} {timestamp_str:<20} {event.point_id:<12} {'---':<15} {'---':<12} {event.message}")
                total_alarm_events += 1

            # Print samples
            for sample in samples:
                timestamp_str = datetime.fromtimestamp(sample.timestamp).strftime("%H:%M:%S.%f")[:-3]

                # Format value based on type
                if isinstance(sample.value, bool) or isinstance(sample.value, int):
                    value_str = str(sample.value)
                else:
                    value_str = f"{sample.value:.2f}"

                # Get alarm state
                alarm_state = alarm_states.get(sample.point_id)
                if alarm_state and alarm_state.is_any_active():
                    alarm_str = f"ALM({alarm_state.get_highest_severity()})"
                else:
                    alarm_str = "OK"

                print(f"{tick_count:<6} {timestamp_str:<20} {sample.point_id:<12} {value_str:<15} {sample.quality.value:<12} {alarm_str:<20}")

            tick_count += 1

            # Sleep until next tick
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n" + "=" * 100)
        print("Simulation stopped by user")

    # Print summary
    elapsed = time.time() - start_time
    print("=" * 100)
    print(f"Total ticks: {tick_count}")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Samples generated: {tick_count * active_count}")
    print(f"Alarm events: {total_alarm_events}")

    # Print historian statistics
    historian.print_statistics()

    print("\n✓ Milestone 4 complete: Historian with deadband/compression")


def cmd_serve(args):
    """Serve command - start HMI web interface."""
    # Load point definitions
    engine = load_and_validate(args.config)

    print("=" * 80)
    print("POINTCORE SIMULATOR - HMI SERVER")
    print("=" * 80)
    print(f"Configuration: {args.config}")
    print(f"Tick interval: {args.interval}s")
    print(f"Server URL: http://{args.host}:{args.port}")
    print("=" * 80)
    print("\nStarting simulation and web server...")
    print("Press Ctrl+C to stop\n")

    # Create and run HMI server
    hmi = HMIServer(engine, tick_interval=args.interval)

    try:
        hmi.run(host=args.host, port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n" + "=" * 80)
        print("Server stopped by user")
        print("\n✓ Milestone 5 complete: Minimal HMI operational")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PointCore-Simulator: SCADA point semantics and lifecycle simulator"
    )

    # Global options
    parser.add_argument(
        "-c", "--config",
        default="config/points.json",
        help="Path to point definitions JSON file (default: config/points.json)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate point definitions")
    validate_parser.add_argument(
        "-d", "--detailed",
        action="store_true",
        help="Show detailed point information"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the simulation")
    run_parser.add_argument(
        "-t", "--ticks",
        type=int,
        default=20,
        help="Number of ticks to run (0 = unlimited, default: 20)"
    )
    run_parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Tick interval in seconds (default: 1.0)"
    )
    run_parser.set_defaults(func=cmd_run)

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start HMI web interface")
    serve_parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Tick interval in seconds (default: 1.0)"
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "-p", "--port",
        type=int,
        default=5000,
        help="Port number (default: 5000)"
    )
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args()

    # If no command specified, default to validate
    if not args.command:
        args.command = "validate"
        args.detailed = False
        args.func = cmd_validate

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
