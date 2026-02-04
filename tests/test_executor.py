"""Tests for task_queue executor module."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime

from task_queue.executor import TaskExecutor, SyncTaskExecutor, create_executor
from task_queue.models import Task, TaskStatus, TaskDocDirectory


class TestTaskExecutor:
    """Tests for TaskExecutor class."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create a mock project root with required directories."""
        reports_dir = tmp_path / "tasks" / "task-reports"
        results_dir = tmp_path / "tasks" / "task-queue" / "results"
        archive_dir = tmp_path / "tasks" / "task-archive"
        docs_dir = tmp_path / "tasks" / "task-documents"

        reports_dir.mkdir(parents=True)
        results_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)
        docs_dir.mkdir(parents=True)

        # Create a task document file
        (docs_dir / "task-20250131-100000-test.md").write_text("# Test Task")

        return tmp_path

    @pytest.fixture
    def task(self, project_root):
        """Create a sample task (file already created by project_root)."""
        return Task(
            task_id="task-20250131-100000-test",
            task_doc_file="tasks/task-documents/task-20250131-100000-test.md",
            task_doc_dir_id="main",
            status=TaskStatus.PENDING
        )

    @pytest.fixture
    def executor(self, project_root):
        """Create a TaskExecutor instance (directories already created)."""
        return TaskExecutor(project_root)

    def test_init_creates_directories(self, executor):
        """Test that initialization creates required directories."""
        assert executor.reports_dir.exists()
        assert executor.results_dir.exists()
        assert executor.archive_dir.exists()

    def test_init_sets_paths(self, executor, project_root):
        """Test that executor sets correct paths."""
        assert executor.project_root == project_root.resolve()
        assert executor.task_docs_dir == project_root / "tasks" / "task-documents"
        assert executor.reports_dir == project_root / "tasks" / "task-reports"
        assert executor.results_dir == project_root / "tasks" / "task-queue"
        assert executor.archive_dir == project_root / "tasks" / "task-archive"

    def test_save_result(self, executor, task):
        """Test saving task result."""
        from task_queue.models import TaskResult

        result = TaskResult(
            task_id=task.task_id,
            task_doc_file=task.task_doc_file,
            task_doc_dir_id=task.task_doc_dir_id,
            status=TaskStatus.COMPLETED,
            started_at="2025-01-31T10:00:00",
            completed_at="2025-01-31T10:00:10",
            duration_seconds=10.0,
            stdout="Task completed",
            cost_usd=0.05
        )

        executor._save_result(result)

        # Check result file was created
        result_file = executor.results_dir / f"{task.task_id}.json"
        assert result_file.exists()

        data = json.loads(result_file.read_text())
        assert data["task_id"] == task.task_id
        assert data["status"] == "completed"

    def test_archive_task_doc(self, executor, project_root):
        """Test archiving a task document."""
        # Create a test file
        doc_file = project_root / "tasks" / "task-documents" / "task-test.md"
        doc_file.write_text("# Test")

        executor._archive_task_doc(doc_file)

        # File should be moved to archive
        archived = executor.archive_dir / "task-test.md"
        assert archived.exists()
        assert not doc_file.exists()

    def test_archive_nonexistent_file(self, executor):
        """Test archiving a non-existent file."""
        # Should not raise error
        nonexistent = Path("/nonexistent/file.md")
        executor._archive_task_doc(nonexistent)
        # No exception raised

    def test_archive_flattens_structure(self, executor, project_root):
        """Test that archive flattens subdirectory structure."""
        # Create a file in a subdirectory
        docs_dir = project_root / "tasks" / "task-documents"
        subdir = docs_dir / "subdir"
        subdir.mkdir(parents=True)
        doc_file = subdir / "task-test.md"
        doc_file.write_text("# Test")

        executor._archive_task_doc(doc_file)

        # Archive should flatten structure (only filename preserved)
        archived = executor.archive_dir / "task-test.md"
        assert archived.exists()
        assert not doc_file.exists()

    def test_task_document_exists(self, executor, task):
        """Test that the task document file can be found."""
        task_path = executor.project_root / task.task_doc_file
        assert task_path.exists()
        assert task_path.read_text() == "# Test Task"


class TestSyncTaskExecutor:
    """Tests for SyncTaskExecutor class."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create a mock project root."""
        reports_dir = tmp_path / "tasks" / "task-reports"
        results_dir = tmp_path / "tasks" / "task-queue" / "results"
        archive_dir = tmp_path / "tasks" / "task-archive"
        docs_dir = tmp_path / "tasks" / "task-documents"

        reports_dir.mkdir(parents=True)
        results_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)
        docs_dir.mkdir(parents=True)

        # Create a task file
        (docs_dir / "task-sync.md").write_text("# Sync Test")

        return tmp_path

    @pytest.fixture
    def sync_executor(self, project_root):
        """Create a SyncTaskExecutor instance."""
        return SyncTaskExecutor(project_root)

    def test_init_creates_executor(self, sync_executor):
        """Test that SyncTaskExecutor creates a TaskExecutor."""
        assert sync_executor._executor is not None
        assert isinstance(sync_executor._executor, TaskExecutor)

    def test_project_root_property(self, sync_executor, project_root):
        """Test that project_root is accessible."""
        assert sync_executor.project_root == project_root.resolve()


class TestCreateExecutor:
    """Tests for create_executor function."""

    def test_create_executor(self, tmp_path):
        """Test creating an executor."""
        (tmp_path / "tasks" / "task-reports").mkdir(parents=True)
        (tmp_path / "tasks" / "task-queue" / "results").mkdir(parents=True)
        (tmp_path / "tasks" / "task-archive").mkdir(parents=True)

        executor = create_executor(tmp_path)

        assert isinstance(executor, SyncTaskExecutor)
        assert executor.project_root == tmp_path.resolve()


class TestTaskExecutorIntegration:
    """Integration tests for TaskExecutor."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create a realistic project structure."""
        reports_dir = tmp_path / "tasks" / "task-reports"
        results_dir = tmp_path / "tasks" / "task-queue" / "results"
        archive_dir = tmp_path / "tasks" / "task-archive"
        docs_dir = tmp_path / "tasks" / "task-documents"

        reports_dir.mkdir(parents=True)
        results_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)
        docs_dir.mkdir(parents=True)

        # Create a valid task file
        (docs_dir / "task-20250131-100000-integration-test.md").write_text("""
# Task: Integration Test

**Status**: pending

---

## Task
Integration test task

## Context
Testing the executor

## Requirements
1. Test requirement
""")

        return tmp_path

    @pytest.fixture
    def executor(self, project_root):
        """Create executor with real file structure."""
        return TaskExecutor(project_root)

    def test_executor_with_real_file_structure(self, executor, project_root):
        """Test executor with real file structure."""
        task_id = "task-20250131-100000-integration-test"
        task = Task(
            task_id=task_id,
            task_doc_file="tasks/task-documents/task-20250131-100000-integration-test.md",
            task_doc_dir_id="main"
        )

        # Verify paths are correct
        assert executor.project_root == project_root.resolve()
        assert executor.task_docs_dir.exists()
        assert executor.archive_dir.exists()

        # Verify task file exists at the right location
        task_path = executor.project_root / task.task_doc_file
        assert task_path.exists()

        # Content should match
        content = task_path.read_text()
        assert "Integration Test" in content

    def test_full_archive_workflow(self, executor, project_root):
        """Test the full workflow of executing and archiving."""
        # Create a task document
        task_id = "task-20250131-120000-archive-test"
        docs_dir = project_root / "tasks" / "task-documents"
        task_file = docs_dir / f"{task_id}.md"
        task_file.write_text("# Archive Test")

        # Verify file exists in docs
        assert task_file.exists()

        # Archive the file
        executor._archive_task_doc(task_file)

        # Verify file moved to archive
        archived_file = executor.archive_dir / f"{task_id}.md"
        assert archived_file.exists()
        assert not task_file.exists()
