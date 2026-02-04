"""Tests for task_queue processor module."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime

from task_queue.processor import TaskProcessor
from task_queue.models import (
    Task, TaskStatus, QueueState, TaskDocDirectory, DiscoveredTask
)


class TestTaskProcessor:
    """Tests for TaskProcessor class."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create a mock project root with required directories."""
        task_queue_dir = tmp_path / "tasks" / "task-queue"
        task_docs_dir = tmp_path / "tasks" / "task-documents"
        archive_dir = tmp_path / "tasks" / "task-archive"

        task_queue_dir.mkdir(parents=True)
        task_docs_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)

        (task_queue_dir / "state").mkdir()
        (task_queue_dir / "results").mkdir()

        return tmp_path

    @pytest.fixture
    def state_file(self, project_root):
        """Create a state file path."""
        return project_root / "tasks" / "task-queue" / "state" / "queue_state.json"

    @pytest.fixture
    def processor(self, project_root, state_file):
        """Create a TaskProcessor instance."""
        with patch('task_queue.processor.TaskScanner'):
            return TaskProcessor(
                project_path=str(project_root),
                state_file=state_file
            )

    @pytest.fixture
    def sample_task_doc_dir(self, project_root):
        """Create a TaskDocDirectory for testing."""
        docs_path = project_root / "tasks" / "task-documents"
        return TaskDocDirectory(
            id="main",
            path=str(docs_path),
            description="Main docs"
        )

    def test_init_creates_directories(self, processor):
        """Test that initialization creates required directories."""
        assert processor.archive_dir.exists()
        assert processor.state_file.parent.exists()

    def test_load_state_default(self, processor):
        """Test loading default state when file doesn't exist."""
        state = processor._load_state()
        assert isinstance(state, QueueState)
        assert state.queue == []

    def test_load_state_from_file(self, processor, state_file):
        """Test loading state from existing file."""
        state_data = {
            "version": "1.0",
            "queue": [
                {
                    "task_id": "test-task",
                    "task_doc_file": "test.md",
                    "task_doc_dir_id": "main",
                    "status": "pending",
                    "source": "load",
                    "added_at": "2025-01-31T10:00:00",
                    "attempts": 0
                }
            ],
            "processing": {
                "is_processing": False,
                "current_task": None
            },
            "statistics": {
                "total_queued": 1,
                "total_completed": 0,
                "total_failed": 0
            },
            "updated_at": "2025-01-31T10:00:00"
        }
        state_file.write_text(json.dumps(state_data))

        state = processor._load_state()
        assert len(state.queue) == 1
        assert state.queue[0].task_id == "test-task"

    def test_load_tasks_scans_directories(self, processor, sample_task_doc_dir):
        """Test that load_tasks scans doc directories."""
        with patch.object(processor.scanner, 'scan_task_doc_directories') as mock_scan:
            mock_task = DiscoveredTask(
                task_id="task-20250131-100000-test",
                task_doc_file=Path("test.md"),
                task_doc_dir_id="main",
                file_hash="abc123",
                file_size=100
            )
            mock_scan.return_value = [mock_task]

            count = processor.load_tasks([sample_task_doc_dir])

            assert count == 1
            mock_scan.assert_called_once()

    def test_load_tasks_adds_to_queue(self, processor, sample_task_doc_dir):
        """Test that loaded tasks are added to the queue."""
        with patch.object(processor.scanner, 'scan_task_doc_directories') as mock_scan:
            mock_task = DiscoveredTask(
                task_id="task-20250131-100000-test",
                task_doc_file=Path("test.md"),
                task_doc_dir_id="main",
                file_hash="abc123",
                file_size=100
            )
            mock_scan.return_value = [mock_task]

            processor.load_tasks([sample_task_doc_dir])

            assert len(processor.state.queue) == 1
            assert processor.state.queue[0].task_id == "task-20250131-100000-test"

    def test_load_tasks_updates_existing_task(self, processor, sample_task_doc_dir):
        """Test that loading updates existing tasks if file changed."""
        # Add existing task
        processor.state.queue.append(Task(
            task_id="task-20250131-100000-test",
            task_doc_file="test.md",
            task_doc_dir_id="main",
            file_hash="oldhash",
            file_size=50
        ))

        with patch.object(processor.scanner, 'scan_task_doc_directories') as mock_scan:
            with patch.object(processor.scanner, 'is_file_modified', return_value=True):
                mock_task = DiscoveredTask(
                    task_id="task-20250131-100000-test",
                    task_doc_file=Path("test.md"),
                    task_doc_dir_id="main",
                    file_hash="newhash",
                    file_size=100
                )
                mock_scan.return_value = [mock_task]

                count = processor.load_tasks([sample_task_doc_dir])

                # Should return 0 because task already exists (just updated)
                assert count == 0

    def test_process_tasks_empty_queue(self, processor):
        """Test processing tasks when queue is empty."""
        result = processor.process_tasks()

        assert result["status"] == "empty"
        assert result["processed"] == 0
        assert result["remaining"] == 0

    def test_process_tasks_with_lock_timeout(self, processor):
        """Test processing when lock is held."""
        # Simulate lock being held
        with patch.object(processor.lock, 'acquire', return_value=False):
            result = processor.process_tasks()

            assert result["status"] == "skipped"
            assert result["reason"] == "locked"

    def test_get_status(self, processor):
        """Test getting processor status."""
        # Add some tasks
        processor.state.queue.append(Task(
            task_id="task-1",
            task_doc_file="test1.md",
            task_doc_dir_id="main",
            status=TaskStatus.PENDING
        ))
        processor.state.queue.append(Task(
            task_id="task-2",
            task_doc_file="test2.md",
            task_doc_dir_id="main",
            status=TaskStatus.COMPLETED
        ))

        status = processor.get_status()

        assert status["project_path"] == str(processor.project_path)
        assert status["queue_stats"]["total"] == 2
        assert status["queue_stats"]["pending"] == 1
        assert status["queue_stats"]["completed"] == 1

    def test_get_queue(self, processor):
        """Test getting all tasks from queue."""
        processor.state.queue.append(Task(
            task_id="test-task",
            task_doc_file="test.md",
            task_doc_dir_id="main"
        ))

        queue = processor.get_queue()

        assert len(queue) == 1
        assert queue[0].task_id == "test-task"
        # Should be a copy, not the same object
        assert queue is not processor.state.queue

    def test_clear_completed(self, processor):
        """Test clearing completed tasks."""
        old_date = datetime.now()
        recent_date = datetime.now()

        # Add completed task with old date
        processor.state.queue.append(Task(
            task_id="old-task",
            task_doc_file="old.md",
            task_doc_dir_id="main",
            status=TaskStatus.COMPLETED,
            completed_at=old_date.isoformat()
        ))

        # Add recent completed task
        processor.state.queue.append(Task(
            task_id="recent-task",
            task_doc_file="recent.md",
            task_doc_dir_id="main",
            status=TaskStatus.COMPLETED,
            completed_at=recent_date.isoformat()
        ))

        # Add pending task
        processor.state.queue.append(Task(
            task_id="pending-task",
            task_doc_file="pending.md",
            task_doc_dir_id="main",
            status=TaskStatus.PENDING
        ))

        # Clear tasks older than 0 days (removes all completed)
        removed = processor.clear_completed(older_than_days=0)

        # Should remove 2 completed tasks
        assert removed == 2
        # Only pending task should remain
        assert len(processor.state.queue) == 1
        assert processor.state.queue[0].task_id == "pending-task"

    def test_archive_task_doc(self, processor, project_root):
        """Test archiving a completed task document."""
        # Create a test file in task-documents
        doc_file = project_root / "tasks" / "task-documents" / "task-test.md"
        doc_file.write_text("# Test Task")

        task = Task(
            task_id="task-test",
            task_doc_file=str(doc_file),
            task_doc_dir_id="main",
            status=TaskStatus.COMPLETED
        )

        processor._archive_task_doc(task)

        # File should be moved to archive
        archived_file = processor.archive_dir / "task-test.md"
        assert archived_file.exists()
        # Original file should be gone
        assert not doc_file.exists()

    def test_archive_nonexistent_file(self, processor):
        """Test archiving when file doesn't exist."""
        task = Task(
            task_id="nonexistent",
            task_doc_file="/nonexistent/file.md",
            task_doc_dir_id="main"
        )

        # Should not raise error
        processor._archive_task_doc(task)

    def test_save_state(self, processor, state_file):
        """Test saving state to file."""
        processor.state.statistics.total_queued = 5

        processor._save_state()

        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["statistics"]["total_queued"] == 5


class TestTaskProcessorIntegration:
    """Integration tests for TaskProcessor."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create a project root with sample tasks."""
        task_queue_dir = tmp_path / "tasks" / "task-queue"
        task_docs_dir = tmp_path / "tasks" / "task-documents"
        archive_dir = tmp_path / "tasks" / "task-archive"

        task_queue_dir.mkdir(parents=True)
        task_docs_dir.mkdir(parents=True)
        archive_dir.mkdir(parents=True)

        (task_queue_dir / "state").mkdir()
        (task_queue_dir / "results").mkdir()

        # Create a valid task file
        (task_docs_dir / "task-20250131-100000-test-task.md").write_text("# Test Task")

        return tmp_path

    @pytest.fixture
    def processor(self, project_root):
        """Create TaskProcessor with real scanner."""
        state_file = project_root / "tasks" / "task-queue" / "state" / "queue_state.json"
        return TaskProcessor(
            project_path=str(project_root),
            state_file=state_file
        )

    def test_full_scan_and_load_workflow(self, processor, project_root):
        """Test scanning and loading tasks end-to-end."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(project_root / "tasks" / "task-documents"),
            description="Main docs"
        )

        count = processor.load_tasks([doc_dir])

        assert count == 1
        assert len(processor.state.queue) == 1
        assert processor.state.queue[0].task_id == "task-20250131-100000-test-task"
