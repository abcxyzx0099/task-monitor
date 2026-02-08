"""
Environment variable names and default values for task-monitor.

All environment variables are optional and have sensible defaults.
"""

import os
from pathlib import Path

# Monitor Configuration
TASK_MONITOR_CONFIG = os.getenv("TASK_MONITOR_CONFIG", "")
TASK_MONITOR_WORKSPACE = os.getenv("TASK_MONITOR_WORKSPACE", "")
TASK_MONITOR_DEFAULT_QUEUE = os.getenv("TASK_MONITOR_DEFAULT_QUEUE", "ad-hoc")

# Monitor Settings
TASK_MONITOR_WATCH_ENABLED = os.getenv("TASK_MONITOR_WATCH_ENABLED", "true").lower() == "true"
TASK_MONITOR_WATCH_DEBOUNCE_MS = int(os.getenv("TASK_MONITOR_WATCH_DEBOUNCE_MS", "500"))
TASK_MONITOR_WATCH_PATTERNS = os.getenv("TASK_MONITOR_WATCH_PATTERNS", "task-*.md").split(",")
TASK_MONITOR_WATCH_RECURSIVE = os.getenv("TASK_MONITOR_WATCH_RECURSIVE", "false").lower() == "true"
TASK_MONITOR_MAX_ATTEMPTS = int(os.getenv("TASK_MONITOR_MAX_ATTEMPTS", "3"))
TASK_MONITOR_ENABLE_FILE_HASH = os.getenv("TASK_MONITOR_ENABLE_FILE_HASH", "true").lower() == "true"

# Default paths
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "task-monitor"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"

# API Keys (loaded from .env)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
