"""Tests for task_monitor.executor module."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from task_monitor.executor import (
    ExecutionResult,
    SyncTaskExecutor,
    create_executor,
)


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_creation(self):
        """Test creating an ExecutionResult."""
        result = ExecutionResult(
            success=True,
            output="Task completed",
            task_id="task-123"
        )
        assert result.success is True
        assert result.output == "Task completed"
        assert result.task_id == "task-123"

    def test_to_dict_with_none_values(self):
        """Test to_dict() filters out None values."""
        result = ExecutionResult(
            success=True,
            task_id="task-123",
            output="Done",
            duration_ms=1000,
            total_cost_usd=None
        )
        data = result.to_dict()
        assert "total_cost_usd" not in data
        assert data["success"] is True
        assert data["duration_ms"] == 1000

    def test_to_dict_complete(self):
        """Test to_dict() with all fields."""
        result = ExecutionResult(
            success=True,
            output="Done",
            error="",  # Empty string is not filtered, only None is
            task_id="task-123",
            duration_ms=1000,
            duration_api_ms=800,
            total_cost_usd=0.001,
            usage={"input_tokens": 100, "output_tokens": 50},
            session_id="sess-123",
            num_turns=3,
            started_at="2026-02-07T12:00:00",
            completed_at="2026-02-07T12:01:00"
        )
        data = result.to_dict()
        # All non-None fields included (12 total since error="" is not None)
        assert len(data) == 12
        assert data["success"] is True
        assert data["usage"]["input_tokens"] == 100
        assert data["error"] == ""

    def test_save_to_file(self, temp_dir):
        """Test save_to_file() creates result JSON."""
        result = ExecutionResult(
            success=True,
            output="Done",
            task_id="task-123",
            duration_ms=1000
        )

        result_path = result.save_to_file(temp_dir, "ad-hoc")

        # Check file exists in correct location
        expected_path = temp_dir / "tasks" / "ad-hoc" / "results" / "task-123.json"
        assert result_path == expected_path
        assert expected_path.exists()

        # Check content
        data = json.loads(expected_path.read_text())
        assert data["success"] is True
        assert data["task_id"] == "task-123"


class TestSyncTaskExecutor:
    """Tests for SyncTaskExecutor class."""

    def test_init_with_workspace(self, temp_dir):
        """Test SyncTaskExecutor initialization with workspace."""
        executor = SyncTaskExecutor(temp_dir)
        assert executor.project_workspace == temp_dir.resolve()

    def test_init_without_workspace(self):
        """Test SyncTaskExecutor initialization without workspace."""
        executor = SyncTaskExecutor()
        assert executor.project_workspace is None

    def test_execute_raises_error_without_workspace(self, temp_dir):
        """Test execute() raises error when project_workspace is not set."""
        executor = SyncTaskExecutor()
        task_file = temp_dir / "task.md"
        task_file.write_text("# Task")

        with pytest.raises(ValueError, match="project_workspace must be set"):
            executor.execute(task_file)

    def test_execute_raises_error_for_nonexistent_task(self, temp_dir):
        """Test execute() raises FileNotFoundError for missing task."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "nonexistent.md"

        with pytest.raises(FileNotFoundError, match="Task document not found"):
            executor.execute(task_file)

    def test_execute_relative_path_resolved(self, temp_dir):
        """Test execute() resolves relative task paths."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "tasks" / "pending" / "task-123.md"
        task_file.parent.mkdir(parents=True)
        task_file.write_text("# Task")

        # Mock the query to avoid actual SDK call
        with patch('task_monitor.executor.query') as mock_query:
            mock_q = MagicMock()
            mock_query.return_value = mock_q

            # Mock message sequence
            async def mock_messages():
                msg = MagicMock()
                msg.subtype = 'success'
                msg.result = "Done"
                msg.duration_ms = 1000
                msg.content = []
                yield msg

            mock_q.__aiter__ = lambda self: mock_messages()

            # Execute with relative path
            result = executor.execute("tasks/pending/task-123.md")

            assert result.task_id == "task-123"

    def test_execute_with_mocked_sdk(self, temp_dir):
        """Test execute() with mocked SDK success path."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "task-123.md"
        task_file.write_text("# Task")

        with patch('task_monitor.executor.query') as mock_query:
            mock_q = MagicMock()
            mock_query.return_value = mock_q

            # Create async generator that yields a success message
            async def mock_messages():
                msg = MagicMock()
                msg.subtype = 'success'
                msg.result = "Task completed successfully"
                msg.duration_ms = 1500
                msg.duration_api_ms = 1200
                msg.total_cost_usd = 0.002
                msg.usage = {"input_tokens": 200, "output_tokens": 100}
                msg.session_id = "test-session"
                msg.num_turns = 5
                msg.content = []
                yield msg

            # Properly set up async iterator
            async def async_iter():
                async for m in mock_messages():
                    yield m

            mock_q.__aiter__ = lambda self: async_iter()

            result = executor.execute(task_file)

            assert result.success is True
            assert result.task_id == "task-123"
            assert result.duration_ms == 1500
            assert result.session_id == "test-session"
            assert result.num_turns == 5

            # Check result file was saved
            result_file = temp_dir / "tasks" / "unknown" / "results" / "task-123.json"
            assert result_file.exists()

    def test_execute_with_sdk_error(self, temp_dir):
        """Test execute() handles SDK error response."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "task-123.md"
        task_file.write_text("# Task")

        with patch('task_monitor.executor.query') as mock_query:
            mock_q = MagicMock()
            mock_query.return_value = mock_q

            # Create async generator that yields an error message
            async def mock_messages():
                msg = MagicMock()
                msg.subtype = 'error'
                msg.result = "SDK execution failed"
                msg.duration_ms = 500
                msg.session_id = "error-session"
                msg.content = []
                yield msg

            async def async_iter():
                async for m in mock_messages():
                    yield m

            mock_q.__aiter__ = lambda self: async_iter()

            result = executor.execute(task_file)

            assert result.success is False
            assert "SDK execution failed" in result.error
            assert result.session_id == "error-session"

            # Result file should still be saved for errors
            result_file = temp_dir / "tasks" / "unknown" / "results" / "task-123.json"
            assert result_file.exists()

    def test_execute_handles_cancelled_error(self, temp_dir):
        """Test execute() handles asyncio.CancelledError."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "task-123.md"
        task_file.write_text("# Task")

        # Patch asyncio.run to raise CancelledError
        with patch('task_monitor.executor.asyncio.run') as mock_run:
            import asyncio
            mock_run.side_effect = asyncio.CancelledError()

            result = executor.execute(task_file)

            assert result.success is False
            assert "cancelled" in result.error.lower()

    def test_execute_handles_general_exception(self, temp_dir):
        """Test execute() handles general exceptions."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "task-123.md"
        task_file.write_text("# Task")

        with patch('task_monitor.executor.query') as mock_query:
            mock_query.side_effect = RuntimeError("Test error")

            result = executor.execute(task_file)

            assert result.success is False
            assert "RuntimeError" in result.error
            assert "Test error" in result.error

    def test_execute_with_custom_worker(self, temp_dir):
        """Test execute() with custom worker parameter."""
        executor = SyncTaskExecutor(temp_dir)
        task_file = temp_dir / "task-123.md"
        task_file.write_text("# Task")

        with patch('task_monitor.executor.query') as mock_query:
            mock_q = MagicMock()
            mock_query.return_value = mock_q

            async def mock_messages():
                msg = MagicMock()
                msg.subtype = 'success'
                msg.result = "Done"
                msg.content = []
                yield msg

            mock_q.__aiter__ = lambda self: mock_messages()

            executor.execute(task_file, worker="planned")

            # Result should be in planned worker directory
            result_file = temp_dir / "tasks" / "planned" / "results" / "task-123.json"
            assert result_file.exists()


class TestCreateExecutor:
    """Tests for create_executor factory function."""

    def test_create_executor(self, temp_dir):
        """Test create_executor() returns configured executor."""
        executor = create_executor(temp_dir)
        assert isinstance(executor, SyncTaskExecutor)
        assert executor.project_workspace == temp_dir.resolve()
