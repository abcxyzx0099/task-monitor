"""Tests for TaskRunner (Directory-Based State Architecture)."""

import pytest
import time
import threading
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from task_queue.task_runner import TaskRunner
from task_queue.models import Queue


class TestTaskRunnerInit:
    """Tests for TaskRunner initialization."""

    def test_init_creates_directories(self, temp_dir):
        """Test that init creates necessary directories."""
        runner = TaskRunner(str(temp_dir))

        # TaskRunner no longer creates directories in __init__
        # Directories are now per-queue (ad-hoc/completed, planned/completed, etc.)
        assert runner.project_workspace == temp_dir.resolve()


class TestPickNextTask:
    """Tests for pick_next_task method."""

    def test_pick_next_task_from_empty_source(self, project_root):
        """Test picking from empty source."""
        runner = TaskRunner(str(project_root))
        queue = Queue(
            id="test",
            path=str(project_root / "tasks" / "ad-hoc")
        )

        task = runner.pick_next_task_from_queue(queue)
        assert task is None

    def test_pick_next_task_from_queue(self, multiple_task_files, project_root):
        """Test picking tasks from a source."""
        runner = TaskRunner(str(project_root))
        queue = Queue(
            id="test",
            path=str(project_root / "tasks" / "ad-hoc")
        )

        # Tasks should be picked in chronological order
        tasks = []
        for _ in range(3):
            task = runner.pick_next_task_from_queue(queue)
            if task:
                tasks.append(task)

        assert len(tasks) == 3
        # Verify they're in chronological order by filename
        task_names = [t.name for t in tasks]
        assert task_names == sorted(task_names)

    def test_pick_next_task_from_multiple_sources(self, project_root):
        """Test picking tasks from multiple sources."""
        # Create two source directories
        source1_dir = project_root / "tasks" / "source1"
        source2_dir = project_root / "tasks" / "source2"
        source1_dir.mkdir(parents=True)
        source2_dir.mkdir(parents=True)

        # Create tasks in both sources
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task1 = source1_dir / f"task-{timestamp}-001-source1.md"
        task2 = source2_dir / f"task-{timestamp}-002-source2.md"
        task1.write_text("# Task 1")
        task2.write_text("# Task 2")

        runner = TaskRunner(str(project_root))
        source1 = Queue(id="source1", path=str(source1_dir))
        source2 = Queue(id="source2", path=str(source2_dir))

        # Pick from all sources - should return the earliest by filename
        task = runner.pick_next_task([source1, source2])
        assert task is not None
        # Should be task-001 since it's earlier in chronological order
        assert "001" in task.name


class TestExecuteTask:
    """Tests for execute_task method."""

    def test_execute_task_moves_to_archive_on_success(self, project_root):
        """Test that successful tasks are moved to completed."""
        runner = TaskRunner(str(project_root))

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = project_root / "tasks" / "ad-hoc" / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        # Per-queue completed directory
        completed_dir = project_root / "tasks" / "ad-hoc" / "completed"

        # Mock the executor to return success
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_queue.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=True,
                task_id=task_file.stem,
                output="Done"
            )

            result = runner.execute_task(task_file, worker="ad-hoc")

            # Task should be in completed
            completed_task = completed_dir / task_file.name
            assert completed_task.exists()
            # Original should be gone
            assert not task_file.exists()
            assert result['status'] == 'success'

    def test_execute_task_moves_to_failed_on_error(self, project_root):
        """Test that failed tasks are moved to failed directory."""
        runner = TaskRunner(str(project_root))

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = project_root / "tasks" / "ad-hoc" / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        # Per-queue failed directory
        failed_dir = project_root / "tasks" / "ad-hoc" / "failed"

        # Mock the executor to return failure
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_queue.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=False,
                task_id=task_file.stem,
                error="Test error"
            )

            result = runner.execute_task(task_file, worker="ad-hoc")

            # Task should be in failed
            failed_task = failed_dir / task_file.name
            assert failed_task.exists()
            assert result['status'] == 'failed'


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_empty(self, project_root):
        """Test status with no tasks."""
        runner = TaskRunner(str(project_root))
        queue = Queue(
            id="test",
            path=str(project_root / "tasks" / "ad-hoc")
        )

        status = runner.get_status([queue])

        assert status['pending'] == 0
        assert status['completed'] == 0
        assert status['failed'] == 0

    def test_get_status_with_pending_tasks(self, multiple_task_files, project_root):
        """Test status with pending tasks."""
        runner = TaskRunner(str(project_root))
        queue = Queue(
            id="test",
            path=str(project_root / "tasks" / "ad-hoc")
        )

        status = runner.get_status([queue])

        assert status['pending'] == 3
        assert 'test' in status['sources']

    def test_get_status_multiple_sources(self, project_root):
        """Test status with multiple source directories."""
        # Create two sources
        source1_dir = project_root / "tasks" / "source1"
        source2_dir = project_root / "tasks" / "source2"
        source1_dir.mkdir(parents=True)
        source2_dir.mkdir(parents=True)

        # Create tasks in source1
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i in range(2):
            task = source1_dir / f"task-{timestamp}-{i:02d}-s1.md"
            task.write_text("# Task")

        # Create tasks in source2
        for i in range(3):
            task = source2_dir / f"task-{timestamp}-{i:02d}-s2.md"
            task.write_text("# Task")

        runner = TaskRunner(str(project_root))
        source1 = Queue(id="source1", path=str(source1_dir))
        source2 = Queue(id="source2", path=str(source2_dir))

        status = runner.get_status([source1, source2])

        assert status['pending'] == 5
        assert status['sources']['source1']['pending'] == 2
        assert status['sources']['source2']['pending'] == 3
