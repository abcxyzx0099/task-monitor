"""Test fixtures for task-monitor tests (Directory-Based State Architecture)."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

from task_monitor.models import (
    MonitorConfig, Queue, MonitorSettings, DiscoveredTask
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def project_root(temp_dir):
    """Create a mock project root with task directories."""
    queue_path = temp_dir / "tasks" / "ad-hoc"
    queue_path.mkdir(parents=True, exist_ok=True)
    (queue_path / "pending").mkdir(exist_ok=True)
    (queue_path / "completed").mkdir(exist_ok=True)
    (queue_path / "failed").mkdir(exist_ok=True)
    (queue_path / "results").mkdir(exist_ok=True)

    return temp_dir


@pytest.fixture
def task_source_dir(project_root):
    """Get the task source directory."""
    return project_root / "tasks" / "ad-hoc" / "pending"


@pytest.fixture
def task_archive_dir(project_root):
    """Get the task archive directory."""
    return project_root / "tasks" / "ad-hoc" / "completed"


@pytest.fixture
def task_failed_dir(project_root):
    """Get the task failed directory."""
    return project_root / "tasks" / "ad-hoc" / "failed"


@pytest.fixture
def sample_queue(temp_dir):
    """Create a sample Queue with proper directory structure."""
    queue_path = temp_dir / "tasks" / "test-queue"
    queue_path.mkdir(parents=True)
    (queue_path / "pending").mkdir(exist_ok=True)
    (queue_path / "completed").mkdir(exist_ok=True)
    (queue_path / "failed").mkdir(exist_ok=True)
    (queue_path / "results").mkdir(exist_ok=True)

    return Queue(
        id="test-queue",
        path=str(queue_path),
        description="Test queue"
    )


@pytest.fixture
def sample_config(temp_dir):
    """Create a sample MonitorConfig with proper queue directory structure."""
    queue_path = temp_dir / "tasks" / "ad-hoc"
    queue_path.mkdir(parents=True)
    (queue_path / "pending").mkdir(exist_ok=True)
    (queue_path / "completed").mkdir(exist_ok=True)
    (queue_path / "failed").mkdir(exist_ok=True)
    (queue_path / "results").mkdir(exist_ok=True)

    return MonitorConfig(
        project_workspace=str(temp_dir),
        queues=[
            Queue(
                id="ad-hoc",
                path=str(queue_path),
                description="Ad-hoc tasks"
            )
        ]
    )


@pytest.fixture
def sample_settings():
    """Create sample MonitorSettings."""
    return MonitorSettings(
        watch_enabled=True,
        watch_debounce_ms=500,
        watch_patterns=["task-*.md"],
        watch_recursive=False
    )


@pytest.fixture
def task_spec_file(temp_dir):
    """Create a sample task specification file."""
    queue_path = temp_dir / "tasks" / "ad-hoc"
    queue_path.mkdir(parents=True)
    pending_dir = queue_path / "pending"
    pending_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_file = pending_dir / f"task-{timestamp}-test-task.md"
    task_file.write_text("""# Task: Test Task

Test task description
""")
    return task_file


@pytest.fixture
def multiple_task_files(temp_dir):
    """Create multiple task specification files."""
    queue_path = temp_dir / "tasks" / "ad-hoc"
    queue_path.mkdir(parents=True, exist_ok=True)
    pending_dir = queue_path / "pending"
    pending_dir.mkdir(exist_ok=True)

    tasks = []
    for i in range(3):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = pending_dir / f"task-{timestamp}-test-{i:02d}.md"
        task_file.write_text(f"# Task: Test Task {i}\n\nTest description\n")
        tasks.append(task_file)
    return tasks
