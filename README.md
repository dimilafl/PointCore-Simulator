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
- [ ] Milestone 2: State generator loop
- [ ] Milestone 3: Alarm engine
- [ ] Milestone 4: Historian with deadband/compression
- [ ] Milestone 5: Minimal HMI
- [ ] Milestone 6: Fault profiles + quality scenarios

## License

MIT
