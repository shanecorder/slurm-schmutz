"""
Schmutz - OOD Job Efficiency Monitor

A CLI utility for displaying Slurm job efficiency metrics,
inspired by jobstats and jobperf.
"""

__version__ = "1.0.0"
__author__ = "Your Name"

from .config import Config
from .job_stats import JobStats, JobMetrics
from .session_card import SessionCardUpdater

__all__ = [
    "Config",
    "JobStats",
    "JobMetrics",
    "SessionCardUpdater",
]
