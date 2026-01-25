"""
Tests for OOD Job Monitor job_stats module.
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest

from ood_job_monitor.job_stats import (
    JobState,
    JobMetrics,
    GPUMetrics,
    JobStats,
)
from ood_job_monitor.config import Config


class TestJobState:
    """Tests for JobState enum."""
    
    def test_from_string_running(self):
        """Test parsing RUNNING state."""
        state = JobState.from_string("RUNNING")
        assert state == JobState.RUNNING
        assert state.is_running is True
        assert state.is_completed is False
    
    def test_from_string_completed(self):
        """Test parsing COMPLETED state."""
        state = JobState.from_string("COMPLETED")
        assert state == JobState.COMPLETED
        assert state.is_running is False
        assert state.is_completed is True
        assert state.is_successful is True
    
    def test_from_string_failed(self):
        """Test parsing FAILED state."""
        state = JobState.from_string("FAILED")
        assert state == JobState.FAILED
        assert state.is_completed is True
        assert state.is_successful is False
    
    def test_from_string_with_extra_text(self):
        """Test parsing state with extra text (e.g., 'CANCELLED by user')."""
        state = JobState.from_string("CANCELLED by user")
        assert state == JobState.CANCELLED
    
    def test_from_string_unknown(self):
        """Test parsing unknown state."""
        state = JobState.from_string("INVALID_STATE")
        assert state == JobState.UNKNOWN
    
    def test_from_string_lowercase(self):
        """Test parsing lowercase state."""
        state = JobState.from_string("running")
        assert state == JobState.RUNNING


class TestJobMetrics:
    """Tests for JobMetrics dataclass."""
    
    def test_default_values(self):
        """Test default metric values."""
        metrics = JobMetrics()
        assert metrics.job_id == ""
        assert metrics.state == JobState.UNKNOWN
        assert metrics.cpu_efficiency == 0.0
    
    def test_elapsed_seconds(self):
        """Test elapsed_seconds property."""
        metrics = JobMetrics(elapsed_time=timedelta(hours=2, minutes=30))
        assert metrics.elapsed_seconds == 9000.0
    
    def test_memory_properties(self):
        """Test memory conversion properties."""
        metrics = JobMetrics(
            memory_requested=4 * 1024**3,  # 4 GB
            memory_used_max=2 * 1024**3,    # 2 GB
        )
        assert metrics.memory_requested_gb == 4.0
        assert metrics.memory_used_max_gb == 2.0
    
    def test_has_gpus(self):
        """Test has_gpus property."""
        metrics = JobMetrics(num_gpus=0)
        assert metrics.has_gpus is False
        
        metrics = JobMetrics(num_gpus=2)
        assert metrics.has_gpus is True
    
    def test_calculate_cpu_efficiency(self):
        """Test CPU efficiency calculation."""
        metrics = JobMetrics(
            elapsed_time=timedelta(hours=1),
            num_cpus=4,
            cpu_time_total=7200,  # 2 hours of CPU time
        )
        metrics.calculate_efficiency()
        # 7200 / (3600 * 4) = 0.5 = 50%
        assert metrics.cpu_efficiency == 50.0
    
    def test_calculate_memory_efficiency(self):
        """Test memory efficiency calculation."""
        metrics = JobMetrics(
            memory_requested=10 * 1024**3,  # 10 GB
            memory_used_max=7 * 1024**3,    # 7 GB
        )
        metrics.calculate_efficiency()
        assert metrics.memory_efficiency == 70.0
    
    def test_efficiency_clamped_to_100(self):
        """Test that efficiency is clamped to 100%."""
        metrics = JobMetrics(
            elapsed_time=timedelta(hours=1),
            num_cpus=1,
            cpu_time_total=7200,  # More CPU time than wall time (hyperthreading?)
        )
        metrics.calculate_efficiency()
        assert metrics.cpu_efficiency == 100.0


class TestGPUMetrics:
    """Tests for GPUMetrics dataclass."""
    
    def test_memory_conversion(self):
        """Test GPU memory conversion to GB."""
        gpu = GPUMetrics(
            memory_used=4 * 1024**3,
            memory_total=16 * 1024**3,
        )
        assert gpu.memory_used_gb == 4.0
        assert gpu.memory_total_gb == 16.0


class TestJobStats:
    """Tests for JobStats class."""
    
    @pytest.fixture
    def job_stats(self):
        """Create JobStats instance with default config."""
        return JobStats(Config())
    
    def test_parse_memory_gigabytes(self, job_stats):
        """Test parsing memory with G suffix."""
        result = job_stats._parse_memory("4G")
        assert result == 4 * 1024**3
    
    def test_parse_memory_megabytes(self, job_stats):
        """Test parsing memory with M suffix."""
        result = job_stats._parse_memory("512M")
        assert result == 512 * 1024**2
    
    def test_parse_memory_kilobytes(self, job_stats):
        """Test parsing memory with K suffix."""
        result = job_stats._parse_memory("1024K")
        assert result == 1024 * 1024
    
    def test_parse_memory_bytes(self, job_stats):
        """Test parsing memory as plain bytes."""
        result = job_stats._parse_memory("1073741824")
        assert result == 1073741824
    
    def test_parse_memory_empty(self, job_stats):
        """Test parsing empty memory string."""
        result = job_stats._parse_memory("")
        assert result == 0.0
    
    def test_parse_time_hours_minutes_seconds(self, job_stats):
        """Test parsing HH:MM:SS format."""
        result = job_stats._parse_time("02:30:45")
        assert result == timedelta(hours=2, minutes=30, seconds=45)
    
    def test_parse_time_days(self, job_stats):
        """Test parsing DD-HH:MM:SS format."""
        result = job_stats._parse_time("1-12:30:00")
        assert result == timedelta(days=1, hours=12, minutes=30)
    
    def test_parse_time_minutes_seconds(self, job_stats):
        """Test parsing MM:SS format."""
        result = job_stats._parse_time("45:30")
        assert result == timedelta(minutes=45, seconds=30)
    
    def test_parse_time_empty(self, job_stats):
        """Test parsing empty time string."""
        result = job_stats._parse_time("")
        assert result == timedelta()
    
    @patch('subprocess.run')
    def test_get_job_state_running(self, mock_run, job_stats):
        """Test getting running job state."""
        mock_run.return_value = MagicMock(
            stdout="RUNNING\n",
            stderr="",
            returncode=0
        )
        
        state = job_stats.get_job_state("12345")
        assert state == JobState.RUNNING
    
    @patch('subprocess.run')
    def test_get_job_state_completed_from_sacct(self, mock_run, job_stats):
        """Test getting completed job state from sacct."""
        # First call to squeue returns empty (job not in queue)
        # Second call to sacct returns COMPLETED
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="", returncode=0),
            MagicMock(stdout="COMPLETED\n", stderr="", returncode=0),
        ]
        
        state = job_stats.get_job_state("12345")
        assert state == JobState.COMPLETED
    
    @patch('subprocess.run')
    def test_run_command_timeout(self, mock_run, job_stats):
        """Test command timeout handling."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        
        stdout, stderr, rc = job_stats._run_command(["test"])
        assert rc == -1
        assert "timed out" in stderr.lower()
