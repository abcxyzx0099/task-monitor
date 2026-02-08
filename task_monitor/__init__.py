"""
Task Monitor - Directory-based state system with watchdog support.

Monitors Queues and executes tasks via Claude Agent SDK.

Architecture: No state file - directory structure is the source of truth.
- tasks/{queue}/pending/   - pending tasks
- tasks/{queue}/completed/ - completed tasks
- tasks/{queue}/failed/    - failed tasks
- tasks/{queue}/results/   - result JSON files
"""

__version__ = "2.0.0"
__author__ = "DataChat Project"

from task_monitor.models import (
    Queue,
    MonitorConfig,
    MonitorSettings,
    DiscoveredTask,
)

from task_monitor.config import ConfigManager, DEFAULT_CONFIG_FILE
from task_monitor.scanner import TaskScanner
from task_monitor.executor import SyncTaskExecutor, create_executor
from task_monitor.task_runner import TaskRunner
from task_monitor.watchdog import WatchdogManager, TaskDocumentWatcher

__all__ = [
    # Models
    "Queue",
    "MonitorConfig",
    "MonitorSettings",
    "DiscoveredTask",
    # Config
    "ConfigManager",
    "DEFAULT_CONFIG_FILE",
    # Components
    "TaskScanner",
    "SyncTaskExecutor",
    "create_executor",
    "TaskRunner",
    "WatchdogManager",
    "TaskDocumentWatcher",
]
