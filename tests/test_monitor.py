"""Tests for task_queue monitor module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from task_queue.monitor import TaskQueue, create_queue
from task_queue.models import QueueConfig, TaskDocDirectory, SystemStatus


class TestTaskQueue:
    """Tests for TaskQueue class."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock ConfigManager."""
        # Use model_construct to bypass validation for test fixtures
        doc_dir = TaskDocDirectory.model_construct(
            id="main",
            path="/tmp/test-project/tasks/task-documents",
            description="Main docs"
        )

        config = QueueConfig(
            project_path="/tmp/test-project",
            task_doc_directories=[doc_dir]
        )
        mock_mgr = MagicMock()
        mock_mgr.config = config
        mock_mgr.config_file = Path("/tmp/config.json")
        return mock_mgr

    @pytest.fixture
    def task_queue(self, mock_config_manager):
        """Create a TaskQueue with mock config."""
        with patch('task_queue.monitor.ConfigManager', return_value=mock_config_manager):
            return TaskQueue(config_manager=mock_config_manager)

    def test_init_with_config_manager(self, mock_config_manager):
        """Test initializing TaskQueue with ConfigManager."""
        with patch('task_queue.monitor.ConfigManager', return_value=mock_config_manager):
            queue = TaskQueue(config_manager=mock_config_manager)

            assert queue.config_manager == mock_config_manager
            assert queue.scanner is not None
            assert queue._processor is None
            assert queue._running is False

    def test_init_without_config_manager(self):
        """Test initializing TaskQueue without ConfigManager."""
        queue = TaskQueue()

        assert queue.config_manager is not None
        assert queue.scanner is not None

    def test_get_processor_creates_processor(self, task_queue):
        """Test that get_processor creates a processor."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            MockProcessor.return_value = mock_processor

            processor = task_queue.get_processor()

            assert processor == mock_processor
            assert task_queue._processor == mock_processor

    def test_get_processor_returns_cached(self, task_queue):
        """Test that get_processor returns cached processor."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            MockProcessor.return_value = mock_processor

            # First call
            processor1 = task_queue.get_processor()
            # Second call
            processor2 = task_queue.get_processor()

            assert processor1 == processor2
            assert MockProcessor.call_count == 1

    def test_get_processor_without_project_path(self, task_queue):
        """Test get_processor when no project path is set."""
        task_queue.config_manager.config.project_path = None

        processor = task_queue.get_processor()

        assert processor is None

    def test_load_tasks_without_project_path(self, task_queue, capsys):
        """Test load_tasks when no project path is set."""
        task_queue.config_manager.config.project_path = None

        result = task_queue.load_tasks()

        assert result == {}
        captured = capsys.readouterr()
        assert "No project path set" in captured.out

    def test_load_tasks_without_doc_dirs(self, task_queue, capsys):
        """Test load_tasks when no doc directories configured."""
        task_queue.config_manager.config.project_path = "/tmp/test"
        task_queue.config_manager.config.task_doc_directories = []

        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            MockProcessor.return_value = mock_processor
            task_queue._processor = mock_processor

            result = task_queue.load_tasks()

            assert result == {}
            captured = capsys.readouterr()
            assert "No task doc directories configured" in captured.out

    def test_load_tasks_success(self, task_queue, mock_config_manager):
        """Test successful task loading."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.load_tasks.return_value = 5
            MockProcessor.return_value = mock_processor

            result = task_queue.load_tasks()

            assert result == {"total": 5}
            mock_processor.load_tasks.assert_called_once()

    def test_process_tasks_without_processor(self, task_queue):
        """Test process_tasks when no processor available."""
        task_queue.config_manager.config.project_path = None

        result = task_queue.process_tasks()

        assert result["status"] == "error"
        assert "No project path configured" in result["error"]

    def test_process_tasks_empty_queue(self, task_queue):
        """Test process_tasks with no pending tasks."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.get_status.return_value = {
                "queue_stats": {"pending": 0}
            }
            mock_processor.process_tasks.return_value = {
                "status": "empty"
            }
            MockProcessor.return_value = mock_processor

            result = task_queue.process_tasks()

            assert result["status"] == "empty"

    def test_process_tasks_with_tasks(self, task_queue):
        """Test process_tasks with pending tasks."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.process_tasks.return_value = {
                "status": "completed",
                "processed": 2,
                "failed": 0,
                "remaining": 1
            }
            MockProcessor.return_value = mock_processor

            result = task_queue.process_tasks()

            assert result["status"] == "completed"
            assert result["processed"] == 2
            assert result["failed"] == 0
            assert result["remaining"] == 1

    def test_run_single_cycle(self, task_queue):
        """Test running a single monitoring cycle."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.process_tasks.return_value = {
                "status": "empty"
            }
            MockProcessor.return_value = mock_processor

            result = task_queue.run_single_cycle()

            assert "process" in result
            mock_processor.process_tasks.assert_called_once()

    def test_run_stops_after_cycles(self, task_queue):
        """Test that run stops after specified cycles."""
        task_queue.config_manager.config.settings.processing_interval = 0

        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.process_tasks.return_value = {"status": "empty"}
            MockProcessor.return_value = mock_processor

            # Run for 2 cycles
            with patch('builtins.input', side_effect=KeyboardInterrupt):
                task_queue.run(cycles=2)

            # Should have processed exactly 2 times
            assert mock_processor.process_tasks.call_count == 2

    def test_stop(self, task_queue):
        """Test stopping the monitor."""
        assert task_queue._running is False

        task_queue._running = True
        task_queue.stop()

        assert task_queue._running is False

    def test_get_status(self, task_queue):
        """Test getting system status."""
        task_queue._running = True
        task_queue._load_count = 5

        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()
            mock_processor.get_status.return_value = {
                "queue_stats": {
                    "pending": 3,
                    "running": 1,
                    "completed": 10,
                    "failed": 2
                }
            }
            task_queue._processor = mock_processor

            status = task_queue.get_status()

            assert isinstance(status, SystemStatus)
            assert status.running is True
            assert status.load_count == 5
            assert status.total_pending == 3
            assert status.total_running == 1
            assert status.total_completed == 10
            assert status.total_failed == 2

    def test_get_task_doc_directory_status(self, task_queue):
        """Test getting status for task doc directories."""
        with patch('task_queue.monitor.TaskProcessor') as MockProcessor:
            mock_processor = MagicMock()

            # Create mock tasks for the configured directory (only "main" is configured)
            mock_task1 = MagicMock()
            mock_task1.task_doc_dir_id = "main"
            mock_task1.status.value = "pending"

            mock_task2 = MagicMock()
            mock_task2.task_doc_dir_id = "main"
            mock_task2.status.value = "completed"

            mock_processor.state.queue = [mock_task1, mock_task2]
            MockProcessor.return_value = mock_processor
            task_queue._processor = mock_processor

            statuses = task_queue.get_task_doc_directory_status()

            # Should return 1 status for the 1 configured directory
            assert len(statuses) == 1
            assert statuses[0].id == "main"
            # Should have both pending and completed counts
            assert statuses[0].queue_stats == {"pending": 1, "completed": 1}


class TestCreateQueue:
    """Tests for create_queue function."""

    def test_create_queue_with_config_file(self, tmp_path):
        """Test creating a queue with a config file."""
        config_file = tmp_path / "config.json"

        with patch('task_queue.monitor.ConfigManager') as MockConfigManager:
            mock_mgr = MagicMock()
            MockConfigManager.return_value = mock_mgr

            queue = create_queue(config_file=config_file)

            assert isinstance(queue, TaskQueue)
            MockConfigManager.assert_called_once()

    def test_create_queue_without_config_file(self):
        """Test creating a queue without a config file."""
        with patch('task_queue.monitor.ConfigManager') as MockConfigManager:
            mock_mgr = MagicMock()
            MockConfigManager.return_value = mock_mgr

            queue = create_queue()

            assert isinstance(queue, TaskQueue)
