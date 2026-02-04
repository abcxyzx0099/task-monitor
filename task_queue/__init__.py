"""
Task Queue - Single project path, multiple task doc directories queue system.

Loads tasks from configured task doc directories and executes them
via Claude Agent SDK with the /task-worker skill.
"""

__version__ = "1.0.0"
__author__ = "DataChat Project"

from task_queue.models import (
    TaskStatus,
    Task,
    TaskResult,
    QueueState,
    Statistics as _Statistics,
    TaskDocDirectory,
    QueueConfig,
    QueueSettings,
    DiscoveredTask,
    SystemStatus,
    TaskDocDirectoryStatus,
)

# Backward compatibility alias
Statistics = _Statistics
ProjectStatistics = _Statistics

from task_queue.config import ConfigManager, DEFAULT_CONFIG_FILE
from task_queue.atomic import AtomicFileWriter, FileLock
from task_queue.scanner import TaskScanner
from task_queue.executor import SyncTaskExecutor, create_executor
from task_queue.processor import TaskProcessor
from task_queue.monitor import TaskQueue, create_queue

__all__ = [
    # Models
    "TaskStatus",
    "Task",
    "TaskResult",
    "QueueState",
    "Statistics",
    "TaskDocDirectory",
    "QueueConfig",
    "QueueSettings",
    "DiscoveredTask",
    "SystemStatus",
    "TaskDocDirectoryStatus",
    "ProjectStatistics",
    # Config
    "ConfigManager",
    "DEFAULT_CONFIG_FILE",
    # Utilities
    "AtomicFileWriter",
    "FileLock",
    # Components
    "TaskScanner",
    "SyncTaskExecutor",
    "create_executor",
    "TaskProcessor",
    "TaskQueue",
    "create_queue",
]
