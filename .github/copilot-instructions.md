# Open OnDemand Job Efficiency Monitor

## Project Overview
This is a Python utility for Open OnDemand that monitors Slurm jobs and updates session cards with job efficiency data. The utility collects CPU, memory, and GPU utilization metrics and displays them in the OOD interface.

## Technology Stack
- **Language**: Python 3.8+
- **Dependencies**: PyYAML for configuration
- **Integration**: Slurm (sstat, sacct, squeue), Open OnDemand session cards
- **Deployment**: systemd service

## Project Structure
```
├── src/
│   └── ood_job_monitor/
│       ├── __init__.py
│       ├── job_stats.py      # Slurm job statistics collection
│       ├── session_card.py   # OOD session card HTML generation
│       ├── monitor.py        # Main monitoring loop
│       └── config.py         # Configuration handling
├── config/
│   └── config.yaml           # Default configuration
├── scripts/
│   └── ood-job-monitor       # CLI entry point
├── systemd/
│   └── ood-job-monitor.service
├── pyproject.toml
└── README.md
```

## Key Features
- Monitors running Slurm jobs every 5 minutes (configurable)
- Collects CPU, memory, GPU utilization using sstat/sacct
- Updates OOD session card info.html files with efficiency metrics
- Color-coded efficiency indicators (green/yellow/red)
- Final job summary when jobs complete
- Supports multi-node and GPU jobs

## Development Guidelines
- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Handle Slurm command failures gracefully
- Log all monitoring activities
- Test with various job types (CPU-only, GPU, multi-node)

## Configuration
Edit `config/config.yaml` to customize:
- Monitoring interval (default: 5 minutes)
- Efficiency thresholds for color coding
- OOD data root path
- Slurm command paths

## Slurm Commands Used
- `sstat` - Running job statistics
- `sacct` - Completed job accounting data
- `squeue` - Job state information
