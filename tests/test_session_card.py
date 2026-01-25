"""
Tests for OOD Job Monitor session_card module.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ood_job_monitor.session_card import SessionCardUpdater
from ood_job_monitor.job_stats import JobMetrics, JobState
from ood_job_monitor.config import Config


class TestSessionCardUpdater:
    """Tests for SessionCardUpdater class."""
    
    @pytest.fixture
    def updater(self):
        """Create SessionCardUpdater with default config."""
        return SessionCardUpdater(Config())
    
    @pytest.fixture
    def running_metrics(self):
        """Create sample metrics for a running job."""
        return JobMetrics(
            job_id="12345",
            job_name="test_job",
            user="testuser",
            state=JobState.RUNNING,
            elapsed_time=timedelta(hours=1, minutes=30),
            time_limit=timedelta(hours=4),
            num_nodes=1,
            num_cpus=8,
            num_gpus=0,
            memory_requested=16 * 1024**3,  # 16 GB
            memory_used_max=8 * 1024**3,    # 8 GB
            cpu_efficiency=75.0,
            memory_efficiency=50.0,
            last_updated=datetime.now(),
        )
    
    @pytest.fixture
    def completed_metrics(self):
        """Create sample metrics for a completed job."""
        return JobMetrics(
            job_id="12345",
            job_name="test_job",
            user="testuser",
            state=JobState.COMPLETED,
            elapsed_time=timedelta(hours=2, minutes=45),
            time_limit=timedelta(hours=4),
            num_nodes=2,
            num_cpus=16,
            num_gpus=2,
            memory_requested=32 * 1024**3,
            memory_used_max=24 * 1024**3,
            cpu_efficiency=85.0,
            memory_efficiency=75.0,
            gpu_utilization_avg=65.0,
            gpu_memory_utilization_avg=45.0,
            last_updated=datetime.now(),
        )
    
    def test_format_duration_hours(self, updater):
        """Test duration formatting with hours."""
        result = updater._format_duration(timedelta(hours=2, minutes=30, seconds=45))
        assert "2h" in result
        assert "30m" in result
    
    def test_format_duration_days(self, updater):
        """Test duration formatting with days."""
        result = updater._format_duration(timedelta(days=1, hours=6))
        assert "1d" in result
        assert "6h" in result
    
    def test_format_duration_negative(self, updater):
        """Test duration formatting with negative value."""
        result = updater._format_duration(timedelta(seconds=-100))
        assert result == "N/A"
    
    def test_format_memory_bytes(self, updater):
        """Test memory formatting."""
        assert "1.0 GB" in updater._format_memory(1024**3)
        assert "512.0 MB" in updater._format_memory(512 * 1024**2)
        assert "1.0 KB" in updater._format_memory(1024)
    
    def test_format_memory_zero(self, updater):
        """Test memory formatting with zero."""
        result = updater._format_memory(0)
        assert result == "N/A"
    
    def test_get_efficiency_class_good(self, updater):
        """Test efficiency class for good values."""
        result = updater._get_efficiency_class(85.0, 80.0, 50.0)
        assert result == "good"
    
    def test_get_efficiency_class_warning(self, updater):
        """Test efficiency class for warning values."""
        result = updater._get_efficiency_class(60.0, 80.0, 50.0)
        assert result == "warning"
    
    def test_get_efficiency_class_poor(self, updater):
        """Test efficiency class for poor values."""
        result = updater._get_efficiency_class(30.0, 80.0, 50.0)
        assert result == "poor"
    
    def test_generate_running_card_html(self, updater, running_metrics):
        """Test generating HTML for running job."""
        html = updater.generate_running_card_html(running_metrics)
        
        assert "Job Efficiency" in html
        assert "CPU Efficiency" in html
        assert "Memory Usage" in html
        assert "75.0%" in html  # CPU efficiency
        assert "50.0%" in html  # Memory efficiency
        assert "<style>" in html
    
    def test_generate_running_card_html_with_gpu(self, updater):
        """Test generating HTML for running job with GPUs."""
        metrics = JobMetrics(
            job_id="12345",
            state=JobState.RUNNING,
            num_gpus=2,
            gpu_utilization_avg=70.0,
            gpu_memory_utilization_avg=50.0,
            elapsed_time=timedelta(hours=1),
            time_limit=timedelta(hours=2),
            last_updated=datetime.now(),
        )
        
        html = updater.generate_running_card_html(metrics)
        
        assert "GPU Utilization" in html
        assert "2 GPUs" in html
        assert "70.0%" in html
    
    def test_generate_completed_card_html(self, updater, completed_metrics):
        """Test generating HTML for completed job."""
        html = updater.generate_completed_card_html(completed_metrics)
        
        assert "Completed Successfully" in html or "✅" in html
        assert "Final CPU Efficiency" in html
        assert "Final Memory Usage" in html
        assert "85.0%" in html  # CPU efficiency
    
    def test_generate_completed_card_html_failed(self, updater):
        """Test generating HTML for failed job."""
        metrics = JobMetrics(
            job_id="12345",
            state=JobState.FAILED,
            elapsed_time=timedelta(hours=1),
            time_limit=timedelta(hours=2),
            last_updated=datetime.now(),
        )
        
        html = updater.generate_completed_card_html(metrics)
        
        assert "Failed" in html or "❌" in html
    
    def test_generate_card_html_dispatches_correctly(self, updater, running_metrics, completed_metrics):
        """Test that generate_card_html dispatches to correct method."""
        running_html = updater.generate_card_html(running_metrics)
        completed_html = updater.generate_card_html(completed_metrics)
        
        # Running job should not have "Final" prefix
        assert "Final CPU" not in running_html
        
        # Completed job should have "Final" prefix
        assert "Final CPU" in completed_html
    
    def test_generate_recommendations_low_cpu(self, updater):
        """Test recommendations for low CPU efficiency."""
        metrics = JobMetrics(
            cpu_efficiency=30.0,
            memory_efficiency=70.0,
        )
        
        recommendations = updater._generate_recommendations(metrics)
        
        assert len(recommendations) > 0
        assert any("CPU" in rec for rec in recommendations)
    
    def test_generate_recommendations_low_memory(self, updater):
        """Test recommendations for low memory usage."""
        metrics = JobMetrics(
            cpu_efficiency=80.0,
            memory_efficiency=20.0,
        )
        
        recommendations = updater._generate_recommendations(metrics)
        
        assert len(recommendations) > 0
        assert any("Memory" in rec or "memory" in rec for rec in recommendations)
    
    def test_generate_recommendations_good_job(self, updater):
        """Test no critical recommendations for good job."""
        metrics = JobMetrics(
            cpu_efficiency=90.0,
            memory_efficiency=75.0,
        )
        
        recommendations = updater._generate_recommendations(metrics)
        
        # Should have no warnings
        assert not any("⚠️" in rec for rec in recommendations)
    
    def test_update_session_card_creates_file(self, updater, running_metrics):
        """Test that update_session_card creates info.html file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = Path(tmpdir)
            
            success = updater.update_session_card(session_path, running_metrics)
            
            assert success is True
            assert (session_path / "info.html").exists()
            
            content = (session_path / "info.html").read_text()
            assert "Job Efficiency" in content
    
    def test_update_session_card_permission_error(self, updater, running_metrics):
        """Test handling of permission errors."""
        # Use a path that should not be writable
        session_path = Path("/nonexistent/path/that/does/not/exist")
        
        success = updater.update_session_card(session_path, running_metrics)
        
        assert success is False


class TestSessionDiscovery:
    """Tests for session discovery functionality."""
    
    @pytest.fixture
    def updater(self):
        """Create SessionCardUpdater with test config."""
        config = Config(
            ood_data_root="/tmp/test_ood",
            session_data_dir="sessions"
        )
        return SessionCardUpdater(config)
    
    def test_list_active_sessions_empty(self, updater):
        """Test listing sessions when directory doesn't exist."""
        sessions = updater.list_active_sessions("nonexistent_user")
        assert sessions == []
    
    def test_find_session_for_job_not_found(self, updater):
        """Test finding session when job doesn't exist."""
        result = updater.find_session_for_job("testuser", "99999")
        assert result is None
    
    def test_list_active_sessions_with_sessions(self, updater):
        """Test listing sessions when sessions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override config path
            updater.config.ood_data_root = tmpdir
            updater.config.session_data_dir = "sessions"
            
            # Create test session structure
            session_path = Path(tmpdir) / "testuser" / "sessions" / "session1"
            session_path.mkdir(parents=True)
            (session_path / "job_id").write_text("12345")
            
            sessions = updater.list_active_sessions("testuser")
            
            assert len(sessions) == 1
            assert sessions[0][1] == "12345"
