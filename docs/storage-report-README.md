# Storage Quota Report Tool

A Python script for generating comprehensive storage quota reports from Isilon quota data files.

## Features

- **Multiple Views:**
  - **Admin View**: Complete overview of all quotas across the system
  - **Per-User View**: Filtered view showing quotas for a specific user
  - **Highlights View**: Shows quotas exceeding thresholds (high usage or low efficiency)

- **Multiple Output Formats:**
  - **Text**: Plain text formatted for terminal display
  - **JSON**: Machine-readable format for integration with other tools
  - **HTML**: Standalone HTML file with styling and interactive features
  - **Markdown**: Standard markdown tables
  - **MDHTML**: Markdown with embedded HTML/CSS (ideal for dashboards like Open OnDemand)

- **Key Metrics:**
  - Total storage used vs allocated
  - Per-quota usage percentages
  - Storage efficiency ratios
  - Identification of quotas over soft/hard limits
  - Highlighting of high usage (>80%) quotas

## Installation

The script is located in `scripts/storage-report` and is self-contained with no external dependencies beyond Python 3.7+.

Make it executable:
```bash
chmod +x scripts/storage-report
```

## Usage

### Admin View (All Quotas)

Show all quotas with summary statistics:

```bash
./scripts/storage-report quotas.txt
```

Output formats:
```bash
# Generate HTML report
./scripts/storage-report quotas.txt --format html -o report.html

# Generate JSON for programmatic access
./scripts/storage-report quotas.txt --format json -o report.json

# Generate Markdown
./scripts/storage-report quotas.txt --format markdown -o report.md

# Generate Markdown with HTML (for OOD dashboards)
./scripts/storage-report quotas.txt --format mdhtml -o status.md
```

### Per-User View

View quotas for a specific user:

```bash
# Basic user view
./scripts/storage-report quotas.txt user USERNAME

# With output format (options can come before OR after the subcommand)
./scripts/storage-report quotas.txt --format html -o user-report.html user USERNAME
# OR
./scripts/storage-report quotas.txt user USERNAME --format html -o user-report.html
```

### Highlights View

Show only high usage or low efficiency quotas:

```bash
# Default thresholds (80% usage, 50% efficiency)
./scripts/storage-report quotas.txt highlights

# Custom thresholds
./scripts/storage-report quotas.txt highlights --usage-threshold 90 --efficiency-threshold 40

# Generate mdhtml for dashboard
./scripts/storage-report quotas.txt --format mdhtml -o highlights.md highlights
```

## Input File Format

The script expects a space-delimited quota file with the following columns:
- Type: quota type (user, directory, default-user, etc.)
- AppliesTo: username or group name
- Path: filesystem path
- Snap: snapshot setting
- Hard: hard limit
- Soft: soft limit
- Adv: advisory limit
- Used: current usage
- Reduction: storage reduction ratio
- Efficiency: deduplication/compression efficiency

Example:
```
Type      AppliesTo  Path                                Snap  Hard   Soft  Adv    Used   Reduction  Efficiency
user      jsmith     /ifs/home/jsmith                    No    1.0T   800G  -      450G   1.2 : 1    1.1 : 1
directory DEFAULT    /ifs/data/lab/bioinfo               No    50.0T  45.0T 40.0T  35.2T  1.5 : 1    1.3 : 1
```

## Output Examples

### Text Output (Terminal)
```
====================================================================================================
  Storage Quota Report - Admin View
====================================================================================================

SUMMARY
----------------------------------------------------------------------------------------------------
Total Entries:        881
Total Hard Limit:     9.4 PB
Total Used:           1.5 PB
Overall Usage:        16.5%
Avg Usage per Quota:  7.2%

Over Hard Limit:      0
Over Soft Limit:      0
High Usage (>80%):    9
----------------------------------------------------------------------------------------------------
```

### JSON Output (Programmable)
```json
{
  "title": "Storage Quota Report - Admin View",
  "summary": {
    "total_entries": 881,
    "total_hard_bytes": 10553751350930307,
    "total_used_bytes": 1740000462113902,
    "overall_usage_pct": 16.5,
    "high_usage_count": 9
  },
  "quotas": [...]
}
```

### MDHTML Output (Dashboard Integration)
Combines markdown syntax with embedded HTML/CSS for rich display in dashboard systems:
- Collapsible details sections
- Color-coded status indicators
- Responsive table layouts
- Inline styling (no external CSS dependencies)

## Integration with Current Status/Efficiency Reports

This script is designed to complement the existing `schmutz` monitoring system:

1. **Placement**: Output goes inline with Current Status and Efficiency Leaders reports
2. **Format Consistency**: Uses the same `mdhtml` format as the sitrep and leaderboard commands
3. **Styling**: Matches the color scheme and styling of existing reports

Example integration in a dashboard:
```bash
# Generate current cluster status
./scripts/schmutz sitrep --format mdhtml -o /dashboard/cluster-status.md

# Generate efficiency leaderboard
./scripts/schmutz leaderboard --format mdhtml -o /dashboard/efficiency.md

# Generate storage quota highlights
./scripts/storage-report quotas.txt --format mdhtml -o /dashboard/storage.md highlights
```

## Options Reference

### Global Options (before subcommand)
- `--format, -f`: Output format (text, json, html, markdown, mdhtml)
- `--output, -o`: Output file path (default: stdout)
- `--quiet, -q`: Suppress progress messages
- `--version, -V`: Show version
- `--help, -h`: Show help message

### Highlights Subcommand Options
- `--usage-threshold`: Usage percentage threshold (default: 80)
- `--efficiency-threshold`: Efficiency percentage threshold (default: 50)

## Examples

### Generate Dashboard Status Page
```bash
# High usage quotas for dashboard
./scripts/storage-report quotas.txt \
  --format mdhtml \
  -o /var/www/dashboard/storage-status.md \
  highlights \
  --usage-threshold 75
```

### User Report Email
```bash
# Generate HTML report for specific user
./scripts/storage-report quotas.txt \
  --format html \
  -o /tmp/user-report.html \
  user jsmith

# Email it
mail -s "Your Storage Quota Report" jsmith@example.com < /tmp/user-report.html
```

### Administrator Daily Summary
```bash
# JSON output for processing
./scripts/storage-report quotas.txt --format json --quiet | \
  jq '.summary | {total_used: .total_used_human, usage_pct: .overall_usage_pct, issues: .high_usage_count}'
```

## Performance

- Parses ~1000 quota entries in <1 second
- JSON output: ~350KB for 881 entries
- HTML output: ~175KB for 881 entries
- Text/Markdown: minimal memory footprint

## Notes

- The script automatically handles size unit conversions (KB, MB, GB, TB, PB)
- Usage percentages are calculated against hard limits
- Entries with no hard limit show 0% usage
- Efficiency ratios are preserved as-is from the input file
