"""
Configuration handling for OOD Job Monitor.

Loads configuration from YAML files and provides defaults.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


@dataclass
class EfficiencyThresholds:
    """Thresholds for color-coded efficiency indicators."""
    
    # CPU efficiency thresholds (percentage)
    cpu_good: float = 80.0
    cpu_warning: float = 50.0
    
    # Memory efficiency thresholds (percentage)
    memory_good: float = 70.0
    memory_warning: float = 40.0
    
    # GPU efficiency thresholds (percentage)
    gpu_good: float = 70.0
    gpu_warning: float = 40.0
    
    # GPU memory thresholds (percentage)
    gpu_memory_good: float = 50.0
    gpu_memory_warning: float = 25.0


@dataclass
class SlurmConfig:
    """Slurm-related configuration."""
    
    # Command paths
    sstat_path: str = "/usr/bin/sstat"
    sacct_path: str = "/usr/bin/sacct"
    squeue_path: str = "/usr/bin/squeue"
    scontrol_path: str = "/usr/bin/scontrol"
    
    # Command timeouts (seconds)
    command_timeout: int = 30


@dataclass
class Config:
    """Main configuration class for Schmutz."""
    
    # OOD paths
    ood_data_root: str = "/var/lib/ondemand-nginx"
    session_data_dir: str = "data/sys/dashboard/batch_connect/db"
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # Thresholds
    thresholds: EfficiencyThresholds = field(default_factory=EfficiencyThresholds)
    
    # Slurm configuration
    slurm: SlurmConfig = field(default_factory=SlurmConfig)
    
    # Session card appearance
    card_title: str = "Job Efficiency"
    show_recommendations: bool = True
    compact_mode: bool = False
    
    @classmethod
    def from_yaml(cls, config_path: str) -> "Config":
        """Load configuration from a YAML file."""
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()
        
        try:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f) or {}
            
            return cls.from_dict(data)
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config file: {e}")
            return cls()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create configuration from a dictionary."""
        # Extract nested configurations
        thresholds_data = data.pop('thresholds', {})
        slurm_data = data.pop('slurm', {})
        
        # Create nested dataclass instances
        thresholds = EfficiencyThresholds(**thresholds_data) if thresholds_data else EfficiencyThresholds()
        slurm = SlurmConfig(**slurm_data) if slurm_data else SlurmConfig()
        
        # Create main config
        return cls(
            thresholds=thresholds,
            slurm=slurm,
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a dictionary."""
        return {
            'ood_data_root': self.ood_data_root,
            'session_data_dir': self.session_data_dir,
            'log_level': self.log_level,
            'log_file': self.log_file,
            'card_title': self.card_title,
            'show_recommendations': self.show_recommendations,
            'compact_mode': self.compact_mode,
            'thresholds': {
                'cpu_good': self.thresholds.cpu_good,
                'cpu_warning': self.thresholds.cpu_warning,
                'memory_good': self.thresholds.memory_good,
                'memory_warning': self.thresholds.memory_warning,
                'gpu_good': self.thresholds.gpu_good,
                'gpu_warning': self.thresholds.gpu_warning,
                'gpu_memory_good': self.thresholds.gpu_memory_good,
                'gpu_memory_warning': self.thresholds.gpu_memory_warning,
            },
            'slurm': {
                'sstat_path': self.slurm.sstat_path,
                'sacct_path': self.slurm.sacct_path,
                'squeue_path': self.slurm.squeue_path,
                'scontrol_path': self.slurm.scontrol_path,
                'command_timeout': self.slurm.command_timeout,
            }
        }
    
    def get_user_session_path(self, username: str) -> Path:
        """Get the OOD session data path for a specific user."""
        return Path(self.ood_data_root) / username / self.session_data_dir
    
    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        
        handlers = [logging.StreamHandler()]
        if self.log_file:
            handlers.append(logging.FileHandler(self.log_file))
        
        logging.basicConfig(
            level=level,
            format=log_format,
            handlers=handlers
        )


def get_default_config_paths() -> list[str]:
    """Return list of default configuration file paths to check."""
    paths = [
        "/etc/schmutz/config.yaml",
        "/etc/schmutz/config.yml",
        os.path.expanduser("~/.config/schmutz/config.yaml"),
        os.path.expanduser("~/.config/schmutz/config.yml"),
        "./config/config.yaml",
        "./config.yaml",
    ]
    return paths


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file or use defaults.
    
    Args:
        config_path: Optional explicit path to config file.
                    If not provided, searches default locations.
    
    Returns:
        Config object with loaded or default settings.
    """
    if config_path:
        return Config.from_yaml(config_path)
    
    # Search default paths
    for path in get_default_config_paths():
        if os.path.exists(path):
            logger.info(f"Loading config from: {path}")
            return Config.from_yaml(path)
    
    logger.info("No config file found, using defaults")
    return Config()
