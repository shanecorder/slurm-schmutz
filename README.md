# Schmutz

A CLI tool for displaying Slurm job efficiency metrics, inspired by [jobstats](https://docs.rcd.clemson.edu/palmetto/job_monitoring/jobstats/) and [jobperf](https://docs.rcd.clemson.edu/palmetto/job_monitoring/jobperf/).

Can also update Open OnDemand session cards with efficiency data.

## Installation

```bash
pip install .
```

## Usage

```bash
# Show efficiency for a job (like jobstats)
schmutz 12345

# Same as above
schmutz status 12345

# With JSON output
schmutz 12345 --json

# Update OOD session card for a job
schmutz update 12345

# List active OOD sessions
schmutz list
```

## Example Output

```
==================================================
Job 12345: my_simulation
==================================================
User:       jsmith
State:      RUNNING
Partition:  compute

--- Resources ---
Nodes:      2
CPUs:       48
Memory:     128.0 GB requested

--- Efficiency ---
CPU:        [████████████████░░░░]  82.3%
Memory:     [██████████░░░░░░░░░░]  51.2% (peak: 65.5 GB)

--- Time ---
Elapsed:    1:23:45
Limit:      4:00:00
Used:       [███████░░░░░░░░░░░░░]  34.9%

--- Recommendations ---
  • Low memory usage (51%). Consider requesting less memory.
```

## Commands

| Command | Description |
|---------|-------------|
| `schmutz <job_id>` | Show job efficiency (default) |
| `schmutz status <job_id>` | Show job efficiency |
| `schmutz update <job_id>` | Update OOD session card |
| `schmutz list` | List active OOD sessions |
| `schmutz html <job_id>` | Generate HTML card |

## Configuration

Optional config file at `/etc/schmutz/config.yaml` or `~/.config/schmutz/config.yaml`:

```yaml
# Efficiency thresholds (percentage)
thresholds:
  cpu_good: 80.0
  cpu_warning: 50.0
  memory_good: 70.0
  memory_warning: 40.0

# OOD paths (for update command)
ood_data_root: /var/lib/ondemand-nginx

# Slurm command paths
slurm:
  sstat_path: /usr/bin/sstat
  sacct_path: /usr/bin/sacct
  squeue_path: /usr/bin/squeue
```

## How It Works

Schmutz is a wrapper around Slurm commands:

- `squeue` - Get job state and resource allocation
- `sstat` - Get real-time stats for running jobs
- `sacct` - Get accounting data for completed jobs

It calculates efficiency as:
- **CPU Efficiency** = (CPU time used) / (wall time × CPUs allocated)
- **Memory Efficiency** = (peak memory used) / (memory requested)

## License

MIT
