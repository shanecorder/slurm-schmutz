"""
Schmutz - CLI for Slurm job efficiency metrics.

Inspired by jobstats and jobperf from Clemson.
"""

import argparse
import json
import logging
import os
import pwd
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .config import Config, load_config
from .job_stats import JobStats
from .session_card import SessionCardUpdater

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging based on command line options."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
    )


def cmd_status(args: argparse.Namespace) -> int:
    """Show efficiency status of a job."""
    config = load_config(args.config)
    job_stats = JobStats(config)
    
    metrics = job_stats.get_job_stats(args.job_id)
    
    if metrics is None:
        print(f"Error: Could not get status for job {args.job_id}", file=sys.stderr)
        return 1
    
    # Print header
    print(f"\n{'='*50}")
    print(f"Job {metrics.job_id}: {metrics.job_name or 'N/A'}")
    print(f"{'='*50}")
    print(f"User:       {metrics.user}")
    print(f"State:      {metrics.state.value}")
    print(f"Partition:  {metrics.partition}")
    
    # Resources
    print(f"\n--- Resources ---")
    print(f"Nodes:      {metrics.num_nodes}")
    print(f"CPUs:       {metrics.num_cpus}")
    if metrics.has_gpus:
        print(f"GPUs:       {metrics.num_gpus}")
    print(f"Memory:     {metrics.memory_requested_gb:.1f} GB requested")
    
    # Efficiency
    print(f"\n--- Efficiency ---")
    cpu_bar = _make_bar(metrics.cpu_efficiency)
    mem_bar = _make_bar(metrics.memory_efficiency)
    print(f"CPU:        {cpu_bar} {metrics.cpu_efficiency:5.1f}%")
    print(f"Memory:     {mem_bar} {metrics.memory_efficiency:5.1f}% (peak: {metrics.memory_used_max_gb:.1f} GB)")
    if metrics.has_gpus:
        gpu_bar = _make_bar(metrics.gpu_utilization_avg)
        print(f"GPU:        {gpu_bar} {metrics.gpu_utilization_avg:5.1f}%")
    
    # Time
    print(f"\n--- Time ---")
    elapsed = str(metrics.elapsed_time).split('.')[0]
    limit = str(metrics.time_limit).split('.')[0]
    time_bar = _make_bar(metrics.time_efficiency)
    print(f"Elapsed:    {elapsed}")
    print(f"Limit:      {limit}")
    print(f"Used:       {time_bar} {metrics.time_efficiency:5.1f}%")
    
    # Recommendations
    recommendations = _get_recommendations(metrics, config)
    if recommendations:
        print(f"\n--- Recommendations ---")
        for rec in recommendations:
            print(f"  • {rec}")
    
    print()
    
    # JSON output if requested
    if args.json:
        data = {
            'job_id': metrics.job_id,
            'job_name': metrics.job_name,
            'user': metrics.user,
            'state': metrics.state.value,
            'partition': metrics.partition,
            'num_nodes': metrics.num_nodes,
            'num_cpus': metrics.num_cpus,
            'num_gpus': metrics.num_gpus,
            'memory_requested_gb': metrics.memory_requested_gb,
            'memory_used_max_gb': metrics.memory_used_max_gb,
            'cpu_efficiency': metrics.cpu_efficiency,
            'memory_efficiency': metrics.memory_efficiency,
            'gpu_utilization': metrics.gpu_utilization_avg if metrics.has_gpus else None,
            'elapsed_seconds': metrics.elapsed_seconds,
            'time_limit_seconds': metrics.time_limit_seconds,
            'time_efficiency': metrics.time_efficiency,
        }
        print("JSON:")
        print(json.dumps(data, indent=2))
    
    return 0


def _make_bar(value: float, width: int = 20) -> str:
    """Create a simple ASCII progress bar."""
    value = max(0, min(100, value))
    filled = int(width * value / 100)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


def _get_recommendations(metrics, config) -> list:
    """Generate efficiency recommendations."""
    recs = []
    thresholds = config.thresholds
    
    if metrics.cpu_efficiency < thresholds.cpu_warning and metrics.cpu_efficiency > 0:
        recs.append(f"Low CPU efficiency ({metrics.cpu_efficiency:.0f}%). Consider requesting fewer CPUs.")
    
    if metrics.memory_efficiency < thresholds.memory_warning and metrics.memory_efficiency > 0:
        recs.append(f"Low memory usage ({metrics.memory_efficiency:.0f}%). Consider requesting less memory.")
    elif metrics.memory_efficiency > 95:
        recs.append(f"High memory usage ({metrics.memory_efficiency:.0f}%). Consider requesting more memory.")
    
    if metrics.has_gpus and metrics.gpu_utilization_avg < thresholds.gpu_warning and metrics.gpu_utilization_avg > 0:
        recs.append(f"Low GPU utilization ({metrics.gpu_utilization_avg:.0f}%). Ensure code is GPU-optimized.")
    
    if metrics.state.is_completed and metrics.time_efficiency < 25:
        recs.append(f"Only used {metrics.time_efficiency:.0f}% of time limit. Request less time for faster scheduling.")
    
    return recs


def cmd_update(args: argparse.Namespace) -> int:
    """Update OOD session card for a job."""
    config = load_config(args.config)
    job_stats = JobStats(config)
    card_updater = SessionCardUpdater(config)
    
    metrics = job_stats.get_job_stats(args.job_id)
    
    if metrics is None:
        print(f"Error: Could not get metrics for job {args.job_id}", file=sys.stderr)
        return 1
    
    if args.session_path:
        session_path = Path(args.session_path)
    else:
        user = args.user or metrics.user
        session_path = card_updater.find_session_for_job(user, args.job_id)
        
        if session_path is None:
            print(f"Error: Could not find OOD session for job {args.job_id}", file=sys.stderr)
            print("Use --session-path to specify the session directory", file=sys.stderr)
            return 1
    
    success = card_updater.update_session_card(session_path, metrics)
    
    if success:
        print(f"Updated session card: {session_path / 'info.html'}")
        return 0
    else:
        print("Error: Failed to update session card", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List active OOD sessions."""
    config = load_config(args.config)
    card_updater = SessionCardUpdater(config)
    job_stats = JobStats(config)
    
    username = args.user or pwd.getpwuid(os.getuid()).pw_name
    sessions = card_updater.list_active_sessions(username)
    
    if not sessions:
        print(f"No active OOD sessions found for user {username}")
        return 0
    
    print(f"\nActive Sessions for {username}")
    print(f"{'Job ID':<12} {'State':<12} {'CPU %':<8} {'Mem %':<8} {'Session'}")
    print("-" * 60)
    
    for session_path, job_id in sessions:
        metrics = job_stats.get_job_stats(job_id)
        if metrics:
            state = metrics.state.value[:10]
            cpu = f"{metrics.cpu_efficiency:.1f}" if metrics.cpu_efficiency > 0 else "-"
            mem = f"{metrics.memory_efficiency:.1f}" if metrics.memory_efficiency > 0 else "-"
        else:
            state = "UNKNOWN"
            cpu = "-"
            mem = "-"
        
        print(f"{job_id:<12} {state:<12} {cpu:<8} {mem:<8} {session_path.name}")
    
    print()
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    """Generate HTML card for a job."""
    config = load_config(args.config)
    job_stats = JobStats(config)
    card_updater = SessionCardUpdater(config)
    
    metrics = job_stats.get_job_stats(args.job_id)
    
    if metrics is None:
        print(f"Error: Could not get metrics for job {args.job_id}", file=sys.stderr)
        return 1
    
    html = card_updater.generate_card_html(metrics)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(html)
        print(f"HTML written to {args.output}")
    else:
        print(html)
    
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog='schmutz',
        description='Display Slurm job efficiency metrics (like jobstats/jobperf)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  schmutz 12345              Show efficiency for job 12345
  schmutz status 12345       Same as above
  schmutz update 12345       Update OOD session card for job
  schmutz list               List active OOD sessions
"""
    )
    
    parser.add_argument(
        '--version', '-V',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Status command (also the default)
    status_parser = subparsers.add_parser('status', help='Show job efficiency status')
    status_parser.add_argument('job_id', help='Slurm job ID')
    status_parser.add_argument('--json', '-j', action='store_true', help='Output JSON')
    status_parser.set_defaults(func=cmd_status)
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update OOD session card')
    update_parser.add_argument('job_id', help='Slurm job ID')
    update_parser.add_argument('--session-path', '-s', help='Path to OOD session directory')
    update_parser.add_argument('--user', '-u', help='Username for finding session')
    update_parser.set_defaults(func=cmd_update)
    
    # List command
    list_parser = subparsers.add_parser('list', help='List active OOD sessions')
    list_parser.add_argument('--user', '-u', help='User to list sessions for')
    list_parser.set_defaults(func=cmd_list)
    
    # HTML command
    html_parser = subparsers.add_parser('html', help='Generate HTML card')
    html_parser.add_argument('job_id', help='Slurm job ID')
    html_parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    html_parser.set_defaults(func=cmd_html)
    
    # Allow bare job_id as first argument (like jobstats)
    parser.add_argument('job_id', nargs='?', help='Slurm job ID (shortcut for status)')
    parser.add_argument('--json', '-j', action='store_true', help='Output JSON (with job_id)')
    
    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    setup_logging(verbose=args.verbose, debug=args.debug)
    
    # Handle bare job_id (schmutz 12345)
    if args.command is None and args.job_id:
        args.command = 'status'
        args.func = cmd_status
        return args.func(args)
    
    if args.command is None:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
