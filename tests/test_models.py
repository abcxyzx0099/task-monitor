"""Tests for task_monitor models (Directory-Based State Architecture)."""

import pytest
from datetime import datetime
from pathlib import Path
from pydantic import ValidationError
import tempfile
import shutil

from task_queue.models import (
    Queue, MonitorSettings, MonitorConfig, DiscoveredTask
)


class TestQueue:
    """Tests for Queue model."""

    def test_create_queue(self):
        """Test creating a Queue."""
        queue = Queue(
            id="test-queue",
            path="/tmp/test/tasks",
            description="Test directory"
        )
        assert queue.id == "test-queue"
        assert queue.path == "/tmp/test/tasks"
        assert queue.description == "Test directory"
        assert queue.added_at is not None

    def test_queue_defaults(self):
        """Test Queue default values."""
        queue = Queue(
            id="test",
            path="/tmp/test"
        )
        assert queue.description == ""
        assert queue.added_at is not None


class TestMonitorSettings:
    """Tests for MonitorSettings model."""

    def test_create_monitor_settings(self):
        """Test creating MonitorSettings."""
        settings = MonitorSettings(
            watch_enabled=True,
            watch_debounce_ms=500,
            watch_patterns=["task-*.md"],
            watch_recursive=False,
            max_attempts=3,
            enable_file_hash=True
        )
        assert settings.watch_enabled is True
        assert settings.watch_debounce_ms == 500
        assert settings.watch_patterns == ["task-*.md"]
        assert settings.watch_recursive is False
        assert settings.max_attempts == 3
        assert settings.enable_file_hash is True

    def test_monitor_settings_defaults(self):
        """Test MonitorSettings default values."""
        settings = MonitorSettings()
        assert settings.watch_enabled is True
        assert settings.watch_debounce_ms == 500
        assert settings.watch_patterns == ["task-*.md"]
        assert settings.watch_recursive is False
        assert settings.max_attempts == 3
        assert settings.enable_file_hash is True


class TestMonitorConfig:
    """Tests for MonitorConfig model."""

    def test_create_monitor_config(self):
        """Test creating MonitorConfig."""
        config = MonitorConfig(
            project_workspace="/tmp/test",
            queues=[
                Queue(
                    id="test",
                    path="/tmp/test/tasks"
                )
            ]
        )
        assert config.version == "2.0"
        assert config.project_workspace == "/tmp/test"
        assert len(config.queues) == 1
        assert isinstance(config.settings, MonitorSettings)

    def test_monitor_config_defaults(self):
        """Test MonitorConfig default values."""
        config = MonitorConfig()
        assert config.version == "2.0"
        assert config.project_workspace is None
        assert config.queues == []
        assert isinstance(config.settings, MonitorSettings)

    def test_get_queue(self, sample_config):
        """Test getting a Queue by ID."""
        queue = sample_config.get_queue("ad-hoc")
        assert queue is not None
        assert queue.id == "ad-hoc"

    def test_get_queue_not_found(self, sample_config):
        """Test getting a non-existent Queue."""
        queue = sample_config.get_queue("non-existent")
        assert queue is None

    def test_add_queue(self, temp_dir):
        """Test adding a Queue."""
        config = MonitorConfig(project_workspace=str(temp_dir))

        queue_path = temp_dir / "tasks" / "test-queue"
        queue_path.mkdir(parents=True)

        queue = config.add_queue(
            path=str(queue_path),
            id="new-queue",
            description="New queue"
        )

        assert queue.id == "new-queue"
        assert len(config.queues) == 1
        assert config.queues[0].id == "new-queue"

    def test_add_queue_duplicate_id(self, temp_dir):
        """Test adding a Queue with duplicate ID."""
        config = MonitorConfig(project_workspace=str(temp_dir))

        queue_path = temp_dir / "tasks"
        queue_path.mkdir(parents=True)

        config.add_queue(
            path=str(queue_path),
            id="test-queue"
        )

        with pytest.raises(ValueError, match="already exists"):
            config.add_queue(
                path=str(queue_path),
                id="test-queue"
            )

    def test_add_queue_invalid_path(self, temp_dir):
        """Test adding a Queue with invalid path."""
        config = MonitorConfig(project_workspace=str(temp_dir))

        with pytest.raises(ValueError, match="does not exist"):
            config.add_queue(
                path="/nonexistent/path",
                id="test"
            )

    def test_remove_queue(self, sample_config):
        """Test removing a Queue."""
        # First add a queue to remove
        config = sample_config
        result = config.remove_queue("ad-hoc")
        assert result is True
        assert len(config.queues) == 0

    def test_remove_queue_not_found(self, sample_config):
        """Test removing a non-existent Queue."""
        result = sample_config.remove_queue("non-existent")
        assert result is False



class TestDiscoveredTask:
    """Tests for DiscoveredTask model."""

    def test_create_discovered_task(self):
        """Test creating a DiscoveredTask."""
        task = DiscoveredTask(
            task_id="task-20250131-100000-test",
            task_doc_file=Path("/tmp/test.md"),
            queue_id="ad-hoc",
            file_hash="abc123",
            file_size=1024,
            discovered_at="2025-01-31T10:00:00"
        )
        assert task.task_id == "task-20250131-100000-test"
        assert task.task_doc_file == Path("/tmp/test.md")
        assert task.queue_id == "ad-hoc"
        assert task.file_hash == "abc123"
        assert task.file_size == 1024

    def test_discovered_task_defaults(self):
        """Test DiscoveredTask default values."""
        task = DiscoveredTask(
            task_id="task-test",
            task_doc_file=Path("/tmp/test.md"),
            queue_id="ad-hoc",
            discovered_at="2025-01-31T10:00:00"
        )
        assert task.file_hash is None
        assert task.file_size == 0
