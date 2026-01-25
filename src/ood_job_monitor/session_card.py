"""
Open OnDemand session card updater.

Generates and updates HTML content for OOD session cards with job efficiency data.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from .config import Config, EfficiencyThresholds
from .job_stats import JobMetrics, JobState

logger = logging.getLogger(__name__)


class SessionCardUpdater:
    """
    Updates Open OnDemand session cards with job efficiency information.
    
    OOD session cards are displayed in the Interactive Sessions view and
    are updated by modifying the info.html file in each session's data directory.
    """
    
    # CSS styles for the efficiency card
    CARD_STYLES = """
<style>
.job-efficiency-card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    line-height: 1.4;
    padding: 10px;
    background: #f8f9fa;
    border-radius: 6px;
    margin: 8px 0;
}
.job-efficiency-card h4 {
    margin: 0 0 10px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #dee2e6;
    color: #495057;
    font-size: 14px;
}
.efficiency-section {
    margin-bottom: 10px;
}
.efficiency-section:last-child {
    margin-bottom: 0;
}
.efficiency-label {
    font-weight: 500;
    color: #6c757d;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.efficiency-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
}
.efficiency-value {
    font-weight: 600;
    font-size: 14px;
}
.efficiency-bar {
    height: 6px;
    background: #e9ecef;
    border-radius: 3px;
    overflow: hidden;
    margin-top: 2px;
}
.efficiency-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
}
.efficiency-good { color: #28a745; }
.efficiency-warning { color: #ffc107; }
.efficiency-poor { color: #dc3545; }
.efficiency-neutral { color: #6c757d; }
.bar-good { background: #28a745; }
.bar-warning { background: #ffc107; }
.bar-poor { background: #dc3545; }
.recommendation {
    margin-top: 10px;
    padding: 8px;
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 4px;
    font-size: 12px;
    color: #856404;
}
.recommendation.good {
    background: #d4edda;
    border-color: #28a745;
    color: #155724;
}
.job-summary {
    margin-top: 10px;
    padding: 8px;
    background: #e9ecef;
    border-radius: 4px;
}
.job-summary-row {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    padding: 2px 0;
}
.last-updated {
    font-size: 10px;
    color: #adb5bd;
    text-align: right;
    margin-top: 8px;
}
.compact .efficiency-row {
    padding: 2px 0;
}
.compact .efficiency-section {
    margin-bottom: 6px;
}
</style>
"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.thresholds = self.config.thresholds
    
    def _get_efficiency_class(self, value: float, good_threshold: float, 
                              warning_threshold: float, invert: bool = False) -> str:
        """
        Get CSS class for efficiency value based on thresholds.
        
        Args:
            value: Efficiency percentage (0-100)
            good_threshold: Threshold for "good" rating
            warning_threshold: Threshold for "warning" rating
            invert: If True, lower values are better (for memory)
            
        Returns:
            CSS class name
        """
        if invert:
            # For inverted metrics, higher is worse
            if value >= good_threshold:
                return "poor"
            elif value >= warning_threshold:
                return "warning"
            else:
                return "good"
        else:
            # Standard: higher is better
            if value >= good_threshold:
                return "good"
            elif value >= warning_threshold:
                return "warning"
            else:
                return "poor"
    
    def _format_duration(self, td: timedelta) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = int(td.total_seconds())
        
        if total_seconds < 0:
            return "N/A"
        
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        
        return " ".join(parts[:3])  # Show at most 3 parts
    
    def _format_memory(self, bytes_val: float) -> str:
        """Format bytes as human-readable string."""
        if bytes_val <= 0:
            return "N/A"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(bytes_val) < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
    
    def _generate_progress_bar(self, value: float, css_class: str) -> str:
        """Generate HTML for a progress bar."""
        value = max(0, min(100, value))  # Clamp to 0-100
        return f"""
        <div class="efficiency-bar">
            <div class="efficiency-bar-fill bar-{css_class}" style="width: {value:.1f}%"></div>
        </div>
        """
    
    def _generate_recommendations(self, metrics: JobMetrics) -> List[str]:
        """Generate efficiency recommendations based on metrics."""
        recommendations = []
        
        # CPU efficiency recommendations
        if metrics.cpu_efficiency < self.thresholds.cpu_warning:
            recommendations.append(
                f"⚠️ CPU efficiency is low ({metrics.cpu_efficiency:.1f}%). "
                f"Consider requesting fewer CPUs or optimizing CPU usage."
            )
        
        # Memory efficiency recommendations
        if metrics.memory_efficiency > 0:
            if metrics.memory_efficiency < self.thresholds.memory_warning:
                recommendations.append(
                    f"⚠️ Memory usage is low ({metrics.memory_efficiency:.1f}%). "
                    f"Consider requesting less memory to improve job scheduling."
                )
            elif metrics.memory_efficiency > 95:
                recommendations.append(
                    f"⚠️ Memory usage is very high ({metrics.memory_efficiency:.1f}%). "
                    f"Consider requesting more memory to avoid out-of-memory errors."
                )
        
        # GPU recommendations
        if metrics.has_gpus and metrics.gpu_utilization_avg > 0:
            if metrics.gpu_utilization_avg < self.thresholds.gpu_warning:
                recommendations.append(
                    f"⚠️ GPU utilization is low ({metrics.gpu_utilization_avg:.1f}%). "
                    f"Ensure your code is properly utilizing GPUs."
                )
        
        # Time efficiency recommendations
        if metrics.time_efficiency > 0 and metrics.time_efficiency < 10:
            recommendations.append(
                f"ℹ️ Job completed using only {metrics.time_efficiency:.1f}% of the time limit. "
                f"Consider reducing the time limit for better scheduling priority."
            )
        
        return recommendations
    
    def generate_running_card_html(self, metrics: JobMetrics) -> str:
        """
        Generate HTML card content for a running job.
        
        Args:
            metrics: Current job metrics
            
        Returns:
            HTML string for the session card
        """
        compact_class = "compact" if self.config.compact_mode else ""
        
        # Determine CSS classes for each metric
        cpu_class = self._get_efficiency_class(
            metrics.cpu_efficiency,
            self.thresholds.cpu_good,
            self.thresholds.cpu_warning
        )
        mem_class = self._get_efficiency_class(
            metrics.memory_efficiency,
            self.thresholds.memory_good,
            self.thresholds.memory_warning
        )
        
        html = f"""
{self.CARD_STYLES}
<div class="job-efficiency-card {compact_class}">
    <h4>📊 {self.config.card_title}</h4>
    
    <div class="efficiency-section">
        <div class="efficiency-label">CPU Efficiency</div>
        <div class="efficiency-row">
            <span>Utilization</span>
            <span class="efficiency-value efficiency-{cpu_class}">{metrics.cpu_efficiency:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.cpu_efficiency, cpu_class)}
    </div>
    
    <div class="efficiency-section">
        <div class="efficiency-label">Memory Usage</div>
        <div class="efficiency-row">
            <span>{self._format_memory(metrics.memory_used_max)} / {self._format_memory(metrics.memory_requested)}</span>
            <span class="efficiency-value efficiency-{mem_class}">{metrics.memory_efficiency:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.memory_efficiency, mem_class)}
    </div>
"""
        
        # Add GPU section if applicable
        if metrics.has_gpus:
            gpu_class = self._get_efficiency_class(
                metrics.gpu_utilization_avg,
                self.thresholds.gpu_good,
                self.thresholds.gpu_warning
            )
            gpu_mem_class = self._get_efficiency_class(
                metrics.gpu_memory_utilization_avg,
                self.thresholds.gpu_memory_good,
                self.thresholds.gpu_memory_warning
            )
            
            html += f"""
    <div class="efficiency-section">
        <div class="efficiency-label">GPU Utilization ({metrics.num_gpus} GPU{'s' if metrics.num_gpus > 1 else ''})</div>
        <div class="efficiency-row">
            <span>Compute</span>
            <span class="efficiency-value efficiency-{gpu_class}">{metrics.gpu_utilization_avg:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.gpu_utilization_avg, gpu_class)}
        <div class="efficiency-row">
            <span>Memory</span>
            <span class="efficiency-value efficiency-{gpu_mem_class}">{metrics.gpu_memory_utilization_avg:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.gpu_memory_utilization_avg, gpu_mem_class)}
    </div>
"""
        
        # Add job summary
        html += f"""
    <div class="job-summary">
        <div class="job-summary-row">
            <span>Elapsed Time:</span>
            <span>{self._format_duration(metrics.elapsed_time)}</span>
        </div>
        <div class="job-summary-row">
            <span>Time Limit:</span>
            <span>{self._format_duration(metrics.time_limit)}</span>
        </div>
        <div class="job-summary-row">
            <span>Resources:</span>
            <span>{metrics.num_nodes}N × {metrics.num_cpus}C</span>
        </div>
    </div>
"""
        
        # Add recommendations if enabled
        if self.config.show_recommendations:
            recommendations = self._generate_recommendations(metrics)
            if recommendations:
                html += """
    <div class="recommendation">
        <strong>Tips:</strong><br>
"""
                for rec in recommendations:
                    html += f"        {rec}<br>\n"
                html += "    </div>\n"
        
        # Add last updated timestamp
        updated_str = metrics.last_updated.strftime("%H:%M:%S") if metrics.last_updated else "Unknown"
        html += f"""
    <div class="last-updated">Last updated: {updated_str}</div>
</div>
"""
        
        return html
    
    def generate_completed_card_html(self, metrics: JobMetrics) -> str:
        """
        Generate HTML card content for a completed job.
        
        Args:
            metrics: Final job metrics
            
        Returns:
            HTML string for the session card
        """
        compact_class = "compact" if self.config.compact_mode else ""
        
        # Determine overall job status
        if metrics.state.is_successful:
            status_icon = "✅"
            status_text = "Completed Successfully"
            status_class = "good"
        elif metrics.state == JobState.CANCELLED:
            status_icon = "🚫"
            status_text = "Cancelled"
            status_class = "warning"
        elif metrics.state == JobState.TIMEOUT:
            status_icon = "⏱️"
            status_text = "Timed Out"
            status_class = "poor"
        else:
            status_icon = "❌"
            status_text = f"Failed ({metrics.state.value})"
            status_class = "poor"
        
        # Determine CSS classes
        cpu_class = self._get_efficiency_class(
            metrics.cpu_efficiency,
            self.thresholds.cpu_good,
            self.thresholds.cpu_warning
        )
        mem_class = self._get_efficiency_class(
            metrics.memory_efficiency,
            self.thresholds.memory_good,
            self.thresholds.memory_warning
        )
        
        html = f"""
{self.CARD_STYLES}
<div class="job-efficiency-card {compact_class}">
    <h4>{status_icon} Job {status_text}</h4>
    
    <div class="job-summary">
        <div class="job-summary-row">
            <span>Job ID:</span>
            <span>{metrics.job_id}</span>
        </div>
        <div class="job-summary-row">
            <span>Total Runtime:</span>
            <span>{self._format_duration(metrics.elapsed_time)}</span>
        </div>
        <div class="job-summary-row">
            <span>Time Limit:</span>
            <span>{self._format_duration(metrics.time_limit)} ({metrics.time_efficiency:.1f}% used)</span>
        </div>
        <div class="job-summary-row">
            <span>Resources:</span>
            <span>{metrics.num_nodes}N × {metrics.num_cpus}C{f' × {metrics.num_gpus}G' if metrics.has_gpus else ''}</span>
        </div>
    </div>
    
    <div class="efficiency-section">
        <div class="efficiency-label">Final CPU Efficiency</div>
        <div class="efficiency-row">
            <span>Overall</span>
            <span class="efficiency-value efficiency-{cpu_class}">{metrics.cpu_efficiency:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.cpu_efficiency, cpu_class)}
    </div>
    
    <div class="efficiency-section">
        <div class="efficiency-label">Final Memory Usage</div>
        <div class="efficiency-row">
            <span>Peak: {self._format_memory(metrics.memory_used_max)} / {self._format_memory(metrics.memory_requested)}</span>
            <span class="efficiency-value efficiency-{mem_class}">{metrics.memory_efficiency:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.memory_efficiency, mem_class)}
    </div>
"""
        
        # Add GPU section if applicable
        if metrics.has_gpus:
            gpu_class = self._get_efficiency_class(
                metrics.gpu_utilization_avg,
                self.thresholds.gpu_good,
                self.thresholds.gpu_warning
            )
            
            html += f"""
    <div class="efficiency-section">
        <div class="efficiency-label">GPU Summary ({metrics.num_gpus} GPU{'s' if metrics.num_gpus > 1 else ''})</div>
        <div class="efficiency-row">
            <span>Average Utilization</span>
            <span class="efficiency-value efficiency-{gpu_class}">{metrics.gpu_utilization_avg:.1f}%</span>
        </div>
        {self._generate_progress_bar(metrics.gpu_utilization_avg, gpu_class)}
    </div>
"""
        
        # Add recommendations for future jobs
        if self.config.show_recommendations:
            recommendations = self._generate_recommendations(metrics)
            if recommendations:
                html += """
    <div class="recommendation">
        <strong>Suggestions for Future Jobs:</strong><br>
"""
                for rec in recommendations:
                    html += f"        {rec}<br>\n"
                html += "    </div>\n"
            elif metrics.cpu_efficiency > self.thresholds.cpu_good and metrics.memory_efficiency > self.thresholds.memory_warning:
                html += """
    <div class="recommendation good">
        ✨ Great job! Resource utilization was efficient.
    </div>
"""
        
        html += "</div>\n"
        
        return html
    
    def generate_card_html(self, metrics: JobMetrics) -> str:
        """
        Generate appropriate HTML card based on job state.
        
        Args:
            metrics: Job metrics
            
        Returns:
            HTML string for the session card
        """
        if metrics.state.is_completed:
            return self.generate_completed_card_html(metrics)
        else:
            return self.generate_running_card_html(metrics)
    
    def update_session_card(self, session_path: Path, metrics: JobMetrics) -> bool:
        """
        Update the session card HTML file with job efficiency data.
        
        Args:
            session_path: Path to the OOD session directory
            metrics: Job metrics to display
            
        Returns:
            True if update was successful, False otherwise
        """
        info_html_path = session_path / "info.html"
        
        try:
            # Generate new HTML content
            new_content = self.generate_card_html(metrics)
            
            # Write to file
            with open(info_html_path, 'w') as f:
                f.write(new_content)
            
            logger.debug(f"Updated session card: {info_html_path}")
            return True
            
        except PermissionError:
            logger.error(f"Permission denied writing to: {info_html_path}")
            return False
        except Exception as e:
            logger.error(f"Error updating session card: {e}")
            return False
    
    def find_session_for_job(self, user: str, job_id: str) -> Optional[Path]:
        """
        Find the OOD session directory for a given Slurm job.
        
        Args:
            user: Username
            job_id: Slurm job ID
            
        Returns:
            Path to session directory or None if not found
        """
        user_session_path = self.config.get_user_session_path(user)
        
        if not user_session_path.exists():
            logger.debug(f"User session path does not exist: {user_session_path}")
            return None
        
        # Search through session directories
        for session_dir in user_session_path.iterdir():
            if not session_dir.is_dir():
                continue
            
            # Check job_id file
            job_id_file = session_dir / "job_id"
            if job_id_file.exists():
                try:
                    with open(job_id_file, 'r') as f:
                        stored_job_id = f.read().strip()
                    
                    if stored_job_id == job_id:
                        return session_dir
                except Exception as e:
                    logger.debug(f"Error reading job_id file: {e}")
                    continue
        
        logger.debug(f"No session found for job {job_id}")
        return None
    
    def list_active_sessions(self, user: str) -> List[tuple]:
        """
        List all active OOD sessions for a user.
        
        Args:
            user: Username
            
        Returns:
            List of (session_path, job_id) tuples
        """
        sessions = []
        user_session_path = self.config.get_user_session_path(user)
        
        if not user_session_path.exists():
            return sessions
        
        for session_dir in user_session_path.iterdir():
            if not session_dir.is_dir():
                continue
            
            job_id_file = session_dir / "job_id"
            if job_id_file.exists():
                try:
                    with open(job_id_file, 'r') as f:
                        job_id = f.read().strip()
                    sessions.append((session_dir, job_id))
                except Exception:
                    continue
        
        return sessions
