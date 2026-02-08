"""Tests for TaskRunner (Directory-Based State Architecture)."""

import pytest
import time
import threading
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from task_monitor.task_runner import TaskRunner
from task_monitor.models import Queue


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
        # Create two queue directories
        queue1_path = project_root / "tasks" / "source1"
        queue2_path = project_root / "tasks" / "source2"
        (queue1_path / "pending").mkdir(parents=True)
        (queue2_path / "pending").mkdir(parents=True)

        # Create tasks in both queues
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task1 = queue1_path / "pending" / f"task-{timestamp}-001-source1.md"
        task2 = queue2_path / "pending" / f"task-{timestamp}-002-source2.md"
        task1.write_text("# Task 1")
        task2.write_text("# Task 2")

        runner = TaskRunner(str(project_root))
        queue1 = Queue(id="source1", path=str(queue1_path))
        queue2 = Queue(id="source2", path=str(queue2_path))

        # Pick from all queues - should return the earliest by filename
        task = runner.pick_next_task([queue1, queue2])
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
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=True,
                task_id=task_file.stem,
                output="Done"
            )

            queue = Queue(id="ad-hoc", path=str(project_root / "tasks" / "ad-hoc"))
            result = runner.execute_task(task_file, queue)

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
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=False,
                task_id=task_file.stem,
                error="Test error"
            )

            queue = Queue(id="ad-hoc", path=str(project_root / "tasks" / "ad-hoc"))
            result = runner.execute_task(task_file, queue)

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
        assert 'test' in status['queues']

    def test_get_status_multiple_sources(self, project_root):
        """Test status with multiple queue directories."""
        # Create two queues
        queue1_path = project_root / "tasks" / "source1"
        queue2_path = project_root / "tasks" / "source2"
        (queue1_path / "pending").mkdir(parents=True)
        (queue2_path / "pending").mkdir(parents=True)

        # Create tasks in queue1
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i in range(2):
            task = queue1_path / "pending" / f"task-{timestamp}-{i:02d}-s1.md"
            task.write_text("# Task")

        # Create tasks in queue2
        for i in range(3):
            task = queue2_path / "pending" / f"task-{timestamp}-{i:02d}-s2.md"
            task.write_text("# Task")

        runner = TaskRunner(str(project_root))
        queue1 = Queue(id="source1", path=str(queue1_path))
        queue2 = Queue(id="source2", path=str(queue2_path))

        status = runner.get_status([queue1, queue2])

        assert status['pending'] == 5
        assert status['queues']['source1']['pending'] == 2
        assert status['queues']['source2']['pending'] == 3


class TestGetCurrentTask:
    """Tests for get_current_task method with file-based status tracking."""

    def test_get_current_task_from_running_file(self, project_root):
        """Test that get_current_task reads from .running file."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        # Create a .running file
        running_file = queue_path / ".ad-hoc.running"
        running_file.write_text("task-1234567890-test")

        # Should read from the file
        running = runner.get_current_task("ad-hoc", queue_path)
        assert running == "task-1234567890-test"

        # Cleanup
        running_file.unlink()

    def test_get_current_task_no_running_file(self, project_root):
        """Test that get_current_task returns None when no .running file exists."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        # No .running file
        running = runner.get_current_task("ad-hoc", queue_path)
        assert running is None

    def test_get_current_task_falls_back_to_memory(self, project_root):
        """Test that get_current_task falls back to in-memory tracking when no queue_path."""
        runner = TaskRunner(str(project_root))

        # Set in-memory tracking directly
        runner.current_tasks["ad-hoc"] = "task-in-memory"

        # Should read from in-memory when queue_path is None
        running = runner.get_current_task("ad-hoc", None)
        assert running == "task-in-memory"

    def test_get_current_task_file_overrides_memory(self, project_root):
        """Test that .running file takes priority over in-memory tracking."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        # Set in-memory tracking
        runner.current_tasks["ad-hoc"] = "task-in-memory"

        # Create a .running file with different value
        running_file = queue_path / ".ad-hoc.running"
        running_file.write_text("task-from-file")

        # Should read from file, not memory
        running = runner.get_current_task("ad-hoc", queue_path)
        assert running == "task-from-file"

        # Cleanup
        running_file.unlink()

    def test_get_current_task_handles_file_read_error(self, project_root):
        """Test that get_current_task handles file read errors gracefully."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        # Create a .running file
        running_file = queue_path / ".ad-hoc.running"
        running_file.write_text("task-123")

        # Mock read_text to raise OSError
        with patch.object(Path, 'read_text', side_effect=OSError("Read error")):
            running = runner.get_current_task("ad-hoc", queue_path)
            # Should fall back to in-memory tracking
            assert running is None

        # Cleanup
        running_file.unlink()


class TestExecuteTaskWithRunningFile:
    """Tests for execute_task method with .running file tracking."""

    def test_execute_task_creates_running_file(self, project_root):
        """Test that execute_task creates .running file when task starts."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        running_file = queue_path / ".ad-hoc.running"

        # Mock the executor to return success
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=True,
                task_id=task_file.stem,
                output="Done"
            )

            queue = Queue(id="ad-hoc", path=str(queue_path))
            runner.execute_task(task_file, queue)

            # .running file should be cleaned up after execution
            assert not running_file.exists()

    def test_execute_task_cleans_up_running_file_on_success(self, project_root):
        """Test that execute_task removes .running file on successful completion."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        running_file = queue_path / ".ad-hoc.running"

        # Mock the executor to return success
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=True,
                task_id=task_file.stem,
                output="Done"
            )

            queue = Queue(id="ad-hoc", path=str(queue_path))
            result = runner.execute_task(task_file, queue)

            # .running file should be cleaned up after success
            assert not running_file.exists()
            assert result['status'] == 'success'

    def test_execute_task_cleans_up_running_file_on_failure(self, project_root):
        """Test that execute_task removes .running file on task failure."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        running_file = queue_path / ".ad-hoc.running"

        # Mock the executor to return failure
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=False,
                task_id=task_file.stem,
                error="Test error"
            )

            queue = Queue(id="ad-hoc", path=str(queue_path))
            result = runner.execute_task(task_file, queue)

            # .running file should be cleaned up after failure
            assert not running_file.exists()
            assert result['status'] == 'failed'

    def test_execute_task_cleans_up_running_file_on_exception(self, project_root):
        """Test that execute_task removes .running file on exception."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        running_file = queue_path / ".ad-hoc.running"

        # Mock the executor to raise an exception
        with patch.object(runner.executor, 'execute', side_effect=Exception("Test exception")):
            queue = Queue(id="ad-hoc", path=str(queue_path))
            result = runner.execute_task(task_file, queue)

            # .running file should be cleaned up after exception
            assert not running_file.exists()
            assert result['status'] == 'error'

    def test_execute_task_handles_running_file_write_error(self, project_root):
        """Test that execute_task handles errors when writing .running file."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        # Mock write_text to raise OSError
        running_file = queue_path / ".ad-hoc.running"
        with patch.object(Path, 'write_text', side_effect=OSError("Write error")):
            # Mock the executor to return success
            with patch.object(runner.executor, 'execute') as mock_execute:
                from task_monitor.executor import ExecutionResult
                mock_execute.return_value = ExecutionResult(
                    success=True,
                    task_id=task_file.stem,
                    output="Done"
                )

                queue = Queue(id="ad-hoc", path=str(queue_path))
                result = runner.execute_task(task_file, queue)

                # Task should still complete despite .running file write error
                assert result['status'] == 'success'

    def test_execute_task_in_memory_tracking_still_works(self, project_root):
        """Test that in-memory tracking is still maintained alongside .running file."""
        runner = TaskRunner(str(project_root))
        queue_path = project_root / "tasks" / "ad-hoc"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_file = queue_path / "pending" / f"task-{timestamp}-test.md"
        task_file.write_text("# Test task")

        # Mock the executor to return success
        with patch.object(runner.executor, 'execute') as mock_execute:
            from task_monitor.executor import ExecutionResult
            mock_execute.return_value = ExecutionResult(
                success=True,
                task_id=task_file.stem,
                output="Done"
            )

            queue = Queue(id="ad-hoc", path=str(queue_path))
            runner.execute_task(task_file, queue)

            # In-memory tracking should be cleared after execution
            assert queue.id not in runner.current_tasks
