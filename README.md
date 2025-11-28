# PointCore-Simulator

SCADA point semantics and lifecycle simulator - a deterministic in-memory state machine with optional persistence.

## Overview

PointCore-Simulator is a focused SCADA-in-a-box implementation that handles:
- Point definition and validation
- Value generation with configurable patterns
- Quality codes and state management
- Alarm evaluation (threshold, ROC, digital)
- Historian with deadband/compression
- Minimal HMI for visualization

### What it does NOT do (by design):
- ❌ PLC logic
- ❌ Real protocols (Modbus/DNP/OPC)
- ❌ Networking
- ❌ External timeseries databases

## Quick Start

### Milestone 1: Point Definitions (Current)

```bash
# Validate point definitions
python main.py

# Show detailed point information
python main.py --detailed

# Use custom config file
python main.py -c path/to/points.json
```

## Architecture

### Components

1. **PointDefinitionEngine** - Loads and validates point configurations from JSON
2. **StateGenerator** - Generates point values using configured patterns (ramp, sine, random walk, etc.)
3. **AlarmEvaluator** - Evaluates alarm conditions and manages state transitions
4. **HistorianLogger** - Records values and events with deadband/compression
5. **MinimalHMI** - Simple web interface for monitoring

### Data Model

**Point Types:**
- `analog` - Continuous values with engineering units
- `digital` - Binary states (0/1)

**Quality Codes:**
- `GOOD` - Normal operation
- `BAD` - Invalid/failed measurement
- `UNCERTAIN` - Questionable quality
- `STALE` - Not updating
- `SIMULATED` - Generated value

## Configuration

Points are defined in `config/points.json`. Example:

```json
{
  "point_id": "PT_101",
  "name": "Feedwater Pressure",
  "type": "analog",
  "eu": "psi",
  "scale": { "eng_min": 0, "eng_max": 300 },
  "flags": { "scan_enabled": true, "alarm_enabled": true },
  "generator": {
    "mode": "ramp",
    "params": { "min": 50, "max": 250, "period_s": 120 }
  },
  "alarm": {
    "hi_hi": 260,
    "hi": 240,
    "lo": 60,
    "lo_lo": 40,
    "roc_threshold": 10.0
  }
}
```

## Development Milestones

- [x] Milestone 1: Point definitions + runtime state
- [x] Milestone 2: State generator loop
- [x] Milestone 3: Alarm engine
- [x] Milestone 4: Historian with deadband/compression
- [x] Milestone 5: Minimal HMI
- [x] Milestone 6: Fault profiles + quality scenarios

## Usage

### Validate Configuration

```bash
python main.py validate
python main.py validate --detailed
```

### Run Console Simulation

```bash
# Run 20 ticks at 1s intervals
python main.py run

# Custom configuration
python main.py run -t 50 -i 0.5
```

### Start Web HMI

```bash
# Start web server on http://127.0.0.1:5000
python main.py serve

# Custom port and config
python main.py -c config/points_with_faults.json serve -p 8080
```

Open http://127.0.0.1:5000 in your browser to view:
- Real-time point summary table
- Interactive trend charts
- Alarm state visualization
- Quality code display

## Fault Profiles

Configure fault injection in point definitions:

**Freeze Value:**
```json
"fault_profile": {
  "type": "freeze_value",
  "params": {"duration_s": 10, "interval_s": 60}
}
```

**Bad Quality Bursts:**
```json
"fault_profile": {
  "type": "bad_quality_bursts",
  "params": {"probability": 0.15, "duration_s": 5}
}
```

**Out-of-Range Spikes:**
```json
"fault_profile": {
  "type": "out_of_range_spike",
  "params": {"probability": 0.1, "multiplier": 1.5}
}
```

## License

MIT
