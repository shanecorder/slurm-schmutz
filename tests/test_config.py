"""
Tests for OOD Job Monitor configuration module.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from ood_job_monitor.config import (
    Config,
    EfficiencyThresholds,
    SlurmConfig,
    load_config,
    get_default_config_paths,
)


class TestEfficiencyThresholds:
    """Tests for EfficiencyThresholds dataclass."""
    
    def test_default_values(self):
        """Test default threshold values."""
        thresholds = EfficiencyThresholds()
        assert thresholds.cpu_good == 80.0
        assert thresholds.cpu_warning == 50.0
        assert thresholds.memory_good == 70.0
        assert thresholds.memory_warning == 40.0
    
    def test_custom_values(self):
        """Test custom threshold values."""
        thresholds = EfficiencyThresholds(cpu_good=90.0, cpu_warning=60.0)
        assert thresholds.cpu_good == 90.0
        assert thresholds.cpu_warning == 60.0


class TestSlurmConfig:
    """Tests for SlurmConfig dataclass."""
    
    def test_default_paths(self):
        """Test default Slurm command paths."""
        slurm = SlurmConfig()
        assert slurm.sstat_path == "/usr/bin/sstat"
        assert slurm.sacct_path == "/usr/bin/sacct"
        assert slurm.command_timeout == 30


class TestConfig:
    """Tests for main Config class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = Config()

        assert config.ood_data_root == "/var/lib/ondemand-nginx"
        assert config.log_level == "INFO"
        assert config.show_recommendations is True
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            'log_level': 'DEBUG',
            'thresholds': {
                'cpu_good': 90.0
            }
        }
        config = Config.from_dict(data)
        assert config.log_level == 'DEBUG'
        assert config.thresholds.cpu_good == 90.0
    
    def test_from_yaml(self):
        """Test loading config from YAML file."""
        yaml_content = """
log_level: WARNING
thresholds:
  cpu_good: 85.0
  memory_warning: 30.0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            config = Config.from_yaml(f.name)
            
            assert config.log_level == 'WARNING'
            assert config.thresholds.cpu_good == 85.0
            assert config.thresholds.memory_warning == 30.0
            
            os.unlink(f.name)
    
    def test_from_yaml_missing_file(self):
        """Test loading config from non-existent file returns defaults."""
        config = Config.from_yaml('/nonexistent/path/config.yaml')
        assert config.ood_data_root == "/var/lib/ondemand-nginx"  # Default value
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = Config()
        data = config.to_dict()
        
        assert 'ood_data_root' in data
        assert 'thresholds' in data
        assert 'slurm' in data
    
    def test_get_user_session_path(self):
        """Test user session path generation."""
        config = Config()
        path = config.get_user_session_path('testuser')
        
        expected = Path('/var/lib/ondemand-nginx/testuser/data/sys/dashboard/batch_connect/db')
        assert path == expected


class TestLoadConfig:
    """Tests for load_config function."""
    
    def test_load_explicit_path(self):
        """Test loading config from explicit path."""
        yaml_content = "log_level: DEBUG"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            config = load_config(f.name)
            assert config.log_level == "DEBUG"
            
            os.unlink(f.name)
    
    def test_load_default_when_no_file(self):
        """Test that defaults are used when no config file exists."""
        config = load_config('/definitely/not/a/real/path.yaml')
        assert isinstance(config, Config)


class TestGetDefaultConfigPaths:
    """Tests for get_default_config_paths function."""
    
    def test_returns_list(self):
        """Test that function returns a list of paths."""
        paths = get_default_config_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0
    
    def test_includes_etc_path(self):
        """Test that /etc path is included."""
        paths = get_default_config_paths()
        assert any('/etc/schmutz' in p for p in paths)
