"""
Slurm job statistics collection module.

Collects CPU, memory, and GPU utilization metrics from running and completed Slurm jobs
using sstat, sacct, and squeue commands.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, SlurmConfig

logger = logging.getLogger(__name__)


class JobState(Enum):
    """Slurm job states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    NODE_FAIL = "NODE_FAIL"
    PREEMPTED = "PREEMPTED"
    UNKNOWN = "UNKNOWN"
    
    @classmethod
    def from_string(cls, state_str: str) -> "JobState":
        """Convert Slurm state string to enum."""
        state_str = state_str.upper().split()[0]  # Handle states like "CANCELLED by user"
        try:
            return cls(state_str)
        except ValueError:
            return cls.UNKNOWN
    
    @property
    def is_running(self) -> bool:
        return self == JobState.RUNNING
    
    @property
    def is_completed(self) -> bool:
        return self in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED,
                       JobState.TIMEOUT, JobState.NODE_FAIL, JobState.PREEMPTED)
    
    @property
    def is_successful(self) -> bool:
        return self == JobState.COMPLETED


@dataclass
class GPUMetrics:
    """GPU utilization metrics."""
    gpu_id: int = 0
    gpu_name: str = ""
    utilization: float = 0.0  # GPU compute utilization (%)
    memory_used: float = 0.0  # Memory used (bytes)
    memory_total: float = 0.0  # Total memory (bytes)
    memory_utilization: float = 0.0  # Memory utilization (%)
    
    @property
    def memory_used_gb(self) -> float:
        return self.memory_used / (1024 ** 3)
    
    @property
    def memory_total_gb(self) -> float:
        return self.memory_total / (1024 ** 3)


@dataclass
class NodeMetrics:
    """Per-node metrics for multi-node jobs."""
    hostname: str = ""
    cpus_allocated: int = 0
    memory_allocated: float = 0.0  # bytes
    cpu_time_used: float = 0.0  # seconds
    memory_used: float = 0.0  # bytes
    memory_max: float = 0.0  # bytes
    gpus: List[GPUMetrics] = field(default_factory=list)


@dataclass
class JobMetrics:
    """Complete job metrics including efficiency calculations."""
    
    # Job identification
    job_id: str = ""
    job_name: str = ""
    user: str = ""
    state: JobState = JobState.UNKNOWN
    
    # Time metrics
    submit_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    elapsed_time: timedelta = field(default_factory=timedelta)
    time_limit: timedelta = field(default_factory=timedelta)
    
    # Resource allocation
    num_nodes: int = 0
    num_cpus: int = 0
    num_gpus: int = 0
    memory_requested: float = 0.0  # bytes
    partition: str = ""
    
    # CPU metrics
    cpu_time_total: float = 0.0  # Total CPU time used (seconds)
    cpu_efficiency: float = 0.0  # Percentage
    
    # Memory metrics
    memory_used_max: float = 0.0  # bytes
    memory_used_avg: float = 0.0  # bytes
    memory_efficiency: float = 0.0  # Percentage
    
    # GPU metrics (aggregated)
    gpu_utilization_avg: float = 0.0  # Percentage
    gpu_memory_utilization_avg: float = 0.0  # Percentage
    gpu_metrics: List[GPUMetrics] = field(default_factory=list)
    
    # Per-node metrics
    node_metrics: List[NodeMetrics] = field(default_factory=list)
    
    # Status
    last_updated: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_time.total_seconds()
    
    @property
    def time_limit_seconds(self) -> float:
        return self.time_limit.total_seconds()
    
    @property
    def time_efficiency(self) -> float:
        """Percentage of time limit used."""
        if self.time_limit_seconds <= 0:
            return 0.0
        return (self.elapsed_seconds / self.time_limit_seconds) * 100
    
    @property
    def memory_requested_gb(self) -> float:
        return self.memory_requested / (1024 ** 3)
    
    @property
    def memory_used_max_gb(self) -> float:
        return self.memory_used_max / (1024 ** 3)
    
    @property
    def has_gpus(self) -> bool:
        return self.num_gpus > 0
    
    def calculate_efficiency(self) -> None:
        """Calculate efficiency metrics from raw data."""
        # CPU efficiency: (CPU time used) / (elapsed time * num CPUs)
        if self.elapsed_seconds > 0 and self.num_cpus > 0:
            max_cpu_time = self.elapsed_seconds * self.num_cpus
            self.cpu_efficiency = (self.cpu_time_total / max_cpu_time) * 100
            self.cpu_efficiency = min(100.0, max(0.0, self.cpu_efficiency))
        
        # Memory efficiency: (max memory used) / (memory requested)
        if self.memory_requested > 0:
            self.memory_efficiency = (self.memory_used_max / self.memory_requested) * 100
            self.memory_efficiency = min(100.0, max(0.0, self.memory_efficiency))
        
        # GPU efficiency (average across all GPUs)
        if self.gpu_metrics:
            self.gpu_utilization_avg = sum(g.utilization for g in self.gpu_metrics) / len(self.gpu_metrics)
            self.gpu_memory_utilization_avg = sum(g.memory_utilization for g in self.gpu_metrics) / len(self.gpu_metrics)


class JobStats:
    """
    Collects job statistics from Slurm.
    
    Uses sstat for running jobs and sacct for completed jobs.
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.slurm = self.config.slurm
    
    def _run_command(self, cmd: List[str], timeout: Optional[int] = None) -> Tuple[str, str, int]:
        """
        Run a shell command and return output.
        
        Returns:
            Tuple of (stdout, stderr, returncode)
        """
        timeout = timeout or self.slurm.command_timeout
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            return "", "Command timed out", -1
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            return "", f"Command not found: {cmd[0]}", -1
        except Exception as e:
            logger.error(f"Error running command {' '.join(cmd)}: {e}")
            return "", str(e), -1
    
    def get_job_state(self, job_id: str) -> JobState:
        """Get the current state of a job."""
        cmd = [
            self.slurm.squeue_path,
            "-j", job_id,
            "--noheader",
            "-o", "%T"
        ]
        stdout, stderr, rc = self._run_command(cmd)
        
        if rc == 0 and stdout.strip():
            return JobState.from_string(stdout.strip())
        
        # Job not in queue, check sacct for final state
        cmd = [
            self.slurm.sacct_path,
            "-j", job_id,
            "--noheader",
            "-P",
            "-o", "State",
            "-n"
        ]
        stdout, stderr, rc = self._run_command(cmd)
        
        if rc == 0 and stdout.strip():
            # sacct may return multiple lines for job steps, get the main job state
            states = stdout.strip().split('\n')
            if states:
                return JobState.from_string(states[0])
        
        return JobState.UNKNOWN
    
    def _parse_memory(self, mem_str: str) -> float:
        """
        Parse Slurm memory string to bytes.
        
        Examples: "1G", "512M", "1024K", "1073741824"
        """
        if not mem_str or mem_str == "":
            return 0.0
        
        mem_str = mem_str.strip().upper()
        
        # Handle suffix notation
        multipliers = {
            'K': 1024,
            'M': 1024 ** 2,
            'G': 1024 ** 3,
            'T': 1024 ** 4,
        }
        
        match = re.match(r'^([\d.]+)([KMGT]?)$', mem_str)
        if match:
            value = float(match.group(1))
            suffix = match.group(2)
            return value * multipliers.get(suffix, 1)
        
        try:
            return float(mem_str)
        except ValueError:
            logger.warning(f"Could not parse memory value: {mem_str}")
            return 0.0
    
    def _parse_time(self, time_str: str) -> timedelta:
        """
        Parse Slurm time string to timedelta.
        
        Formats: "DD-HH:MM:SS", "HH:MM:SS", "MM:SS", "SS"
        """
        if not time_str or time_str == "":
            return timedelta()
        
        time_str = time_str.strip()
        
        days = 0
        if '-' in time_str:
            days_part, time_str = time_str.split('-', 1)
            days = int(days_part)
        
        parts = time_str.split(':')
        
        try:
            if len(parts) == 3:
                hours, minutes, seconds = map(float, parts)
            elif len(parts) == 2:
                hours = 0
                minutes, seconds = map(float, parts)
            elif len(parts) == 1:
                hours = 0
                minutes = 0
                seconds = float(parts[0])
            else:
                return timedelta()
            
            return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        except ValueError:
            logger.warning(f"Could not parse time value: {time_str}")
            return timedelta()
    
    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse Slurm datetime string."""
        if not dt_str or dt_str in ("Unknown", "None", "N/A"):
            return None
        
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(dt_str.strip(), fmt)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse datetime: {dt_str}")
        return None
    
    def _parse_cpu_time(self, cpu_time_str: str) -> float:
        """Parse CPU time to seconds."""
        td = self._parse_time(cpu_time_str)
        return td.total_seconds()
    
    def get_running_job_stats(self, job_id: str) -> Optional[JobMetrics]:
        """
        Get statistics for a running job using sstat.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            JobMetrics object or None if job not found/error
        """
        metrics = JobMetrics(job_id=job_id, state=JobState.RUNNING)
        metrics.last_updated = datetime.now()
        
        # First get job info from squeue
        squeue_cmd = [
            self.slurm.squeue_path,
            "-j", job_id,
            "--noheader",
            "-o", "%j|%u|%T|%V|%S|%L|%D|%C|%b|%m|%P"  # name|user|state|submit|start|timeleft|nodes|cpus|gres|memory|partition
        ]
        stdout, stderr, rc = self._run_command(squeue_cmd)
        
        if rc != 0 or not stdout.strip():
            logger.warning(f"Job {job_id} not found in squeue")
            return None
        
        parts = stdout.strip().split('|')
        if len(parts) >= 11:
            metrics.job_name = parts[0]
            metrics.user = parts[1]
            metrics.state = JobState.from_string(parts[2])
            metrics.submit_time = self._parse_datetime(parts[3])
            metrics.start_time = self._parse_datetime(parts[4])
            # Time left -> calculate elapsed and limit
            time_left = self._parse_time(parts[5])
            metrics.num_nodes = int(parts[6]) if parts[6].isdigit() else 1
            metrics.num_cpus = int(parts[7]) if parts[7].isdigit() else 1
            
            # Parse GRES for GPUs
            gres = parts[8]
            if 'gpu' in gres.lower():
                match = re.search(r'gpu[:\w]*:(\d+)', gres.lower())
                if match:
                    metrics.num_gpus = int(match.group(1))
            
            metrics.memory_requested = self._parse_memory(parts[9])
            metrics.partition = parts[10]
            
            # Calculate elapsed time
            if metrics.start_time:
                metrics.elapsed_time = datetime.now() - metrics.start_time
                metrics.time_limit = metrics.elapsed_time + time_left
        
        # Get detailed stats using sstat
        # Note: sstat requires job steps, try both .batch and .0
        for step_suffix in ["", ".batch", ".0"]:
            sstat_cmd = [
                self.slurm.sstat_path,
                "-j", f"{job_id}{step_suffix}",
                "--noheader",
                "-P",
                "-o", "JobID,AveCPU,MaxRSS,MaxVMSize,NTasks"
            ]
            stdout, stderr, rc = self._run_command(sstat_cmd)
            
            if rc == 0 and stdout.strip():
                for line in stdout.strip().split('\n'):
                    parts = line.split('|')
                    if len(parts) >= 5:
                        metrics.cpu_time_total = self._parse_cpu_time(parts[1])
                        metrics.memory_used_max = self._parse_memory(parts[2])
                        break
                break
        
        # Calculate efficiencies
        metrics.calculate_efficiency()
        
        return metrics
    
    def get_completed_job_stats(self, job_id: str) -> Optional[JobMetrics]:
        """
        Get statistics for a completed job using sacct.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            JobMetrics object or None if job not found/error
        """
        metrics = JobMetrics(job_id=job_id)
        metrics.last_updated = datetime.now()
        
        # Get comprehensive job info from sacct
        sacct_cmd = [
            self.slurm.sacct_path,
            "-j", job_id,
            "--noheader",
            "-P",
            "-o", "JobID,JobName,User,State,Submit,Start,End,Elapsed,Timelimit,"
                  "NNodes,NCPUs,ReqMem,MaxRSS,AveCPU,TotalCPU,Partition,AllocGRES,ExitCode"
        ]
        stdout, stderr, rc = self._run_command(sacct_cmd)
        
        if rc != 0 or not stdout.strip():
            logger.warning(f"Job {job_id} not found in sacct: {stderr}")
            return None
        
        # Parse main job record (first line without step suffix)
        lines = stdout.strip().split('\n')
        main_line = None
        batch_line = None
        
        for line in lines:
            parts = line.split('|')
            if parts:
                step_id = parts[0]
                if step_id == job_id or step_id == f"{job_id}.batch":
                    if '.batch' in step_id:
                        batch_line = parts
                    else:
                        main_line = parts
        
        if not main_line:
            main_line = lines[0].split('|') if lines else None
        
        if not main_line or len(main_line) < 18:
            logger.warning(f"Incomplete sacct output for job {job_id}")
            return None
        
        # Parse main job info
        metrics.job_name = main_line[1]
        metrics.user = main_line[2]
        metrics.state = JobState.from_string(main_line[3])
        metrics.submit_time = self._parse_datetime(main_line[4])
        metrics.start_time = self._parse_datetime(main_line[5])
        metrics.end_time = self._parse_datetime(main_line[6])
        metrics.elapsed_time = self._parse_time(main_line[7])
        metrics.time_limit = self._parse_time(main_line[8])
        metrics.num_nodes = int(main_line[9]) if main_line[9].isdigit() else 1
        metrics.num_cpus = int(main_line[10]) if main_line[10].isdigit() else 1
        
        # Parse requested memory (may include 'n' or 'c' suffix for per-node or per-cpu)
        req_mem = main_line[11]
        mem_multiplier = 1
        if req_mem.endswith('n'):
            mem_multiplier = metrics.num_nodes
            req_mem = req_mem[:-1]
        elif req_mem.endswith('c'):
            mem_multiplier = metrics.num_cpus
            req_mem = req_mem[:-1]
        metrics.memory_requested = self._parse_memory(req_mem) * mem_multiplier
        
        metrics.partition = main_line[15]
        
        # Parse GPU allocation
        alloc_gres = main_line[16] if len(main_line) > 16 else ""
        if 'gpu' in alloc_gres.lower():
            match = re.search(r'gpu[:\w]*:(\d+)', alloc_gres.lower())
            if match:
                metrics.num_gpus = int(match.group(1))
        
        # Get memory and CPU stats from batch step if available
        if batch_line and len(batch_line) >= 15:
            metrics.memory_used_max = self._parse_memory(batch_line[12])
            metrics.cpu_time_total = self._parse_cpu_time(batch_line[14])
        else:
            metrics.memory_used_max = self._parse_memory(main_line[12])
            metrics.cpu_time_total = self._parse_cpu_time(main_line[14])
        
        # Calculate efficiencies
        metrics.calculate_efficiency()
        
        return metrics
    
    def get_job_stats(self, job_id: str) -> Optional[JobMetrics]:
        """
        Get job statistics regardless of job state.
        
        Automatically detects if job is running or completed and uses
        the appropriate method.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            JobMetrics object or None if job not found/error
        """
        state = self.get_job_state(job_id)
        
        if state.is_running:
            return self.get_running_job_stats(job_id)
        elif state.is_completed:
            return self.get_completed_job_stats(job_id)
        elif state == JobState.PENDING:
            # Job is pending, return minimal info
            metrics = JobMetrics(job_id=job_id, state=state)
            metrics.last_updated = datetime.now()
            return metrics
        else:
            # Try sacct first for unknown states
            result = self.get_completed_job_stats(job_id)
            if result:
                return result
            # Fall back to trying sstat
            return self.get_running_job_stats(job_id)
    
    def get_gpu_stats(self, job_id: str, node_list: Optional[List[str]] = None) -> List[GPUMetrics]:
        """
        Get GPU utilization statistics for a job.
        
        This requires nvidia-smi or similar tools on the compute nodes.
        For now, we'll try to parse from Slurm TRES data if available.
        
        Note: Full GPU monitoring may require additional setup like
        nvidia-dcgm or custom monitoring scripts on compute nodes.
        
        Args:
            job_id: Slurm job ID
            node_list: Optional list of nodes to query
            
        Returns:
            List of GPUMetrics for each GPU in the job
        """
        gpu_metrics = []
        
        # Try to get GPU stats from sacct TRES
        sacct_cmd = [
            self.slurm.sacct_path,
            "-j", job_id,
            "--noheader",
            "-P",
            "-o", "TRESUsageInTot,TRESUsageInMax"
        ]
        stdout, stderr, rc = self._run_command(sacct_cmd)
        
        if rc == 0 and stdout.strip():
            # Parse TRES data for GPU info
            # Format varies by Slurm version and configuration
            for line in stdout.strip().split('\n'):
                if 'gres/gpu' in line.lower():
                    # Try to extract GPU utilization from TRES
                    # This is highly dependent on site configuration
                    pass
        
        return gpu_metrics
