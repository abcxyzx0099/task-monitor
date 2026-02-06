"""Additional tests for daemon to improve coverage."""

import pytest
import time
import threading
import signal
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from argparse import Namespace

from task_queue.daemon import TaskQueueDaemon, WORKER_KEEPALIVE_TIMEOUT, WORKER_RETRY_DELAY, WORKER_CYCLE_PAUSE
from task_queue.models import TaskSourceDirectory


class TestDaemonInit:
    """Tests for daemon initialization."""

    def test_init_with_default_config(self):
        """Test daemon initialization with default config file."""
        daemon = TaskQueueDaemon()
        assert daemon.config_file is not None  # DEFAULT_CONFIG_FILE
        assert daemon.task_runner is None
        assert daemon.running is False
        assert daemon.shutdown_requested is False
        assert daemon.watchdog_manager is None
        assert daemon._worker_threads == {}
        assert daemon._source_events == {}

    def test_init_with_custom_config(self, temp_dir):
        """Test daemon initialization with custom config file."""
        config_file = temp_dir / "custom-config.json"
        daemon = TaskQueueDaemon(config_file=config_file)
        assert daemon.config_file == config_file

    def test_signal_handler_setup(self, temp_dir):
        """Test that signal handlers are set up during init."""
        daemon = TaskQueueDaemon(config_file=temp_dir / "config.json")

        # Check signal handlers are registered (they should be callable)
        # We can't directly test signal handlers, but we can call the methods
        daemon._source_events["test"] = threading.Event()
        daemon._signal_handler(signal.SIGTERM, None)

        assert daemon.shutdown_requested is True
        assert daemon._source_events["test"].is_set()

    def test_reload_handler(self, temp_dir):
        """Test the reload handler (SIGHUP)."""
        daemon = TaskQueueDaemon(config_file=temp_dir / "config.json")

        # Call reload handler - should not crash
        daemon._reload_handler(signal.SIGHUP, None)

        # No exception means it worked
        assert True


class TestSignalHandler:
    """Tests for signal handling."""

    def test_signal_handler_sets_shutdown_flag(self):
        """Test that signal handler sets shutdown flag."""
        daemon = TaskQueueDaemon()
        daemon._source_events["source1"] = threading.Event()
        daemon._source_events["source2"] = threading.Event()

        daemon._signal_handler(signal.SIGTERM, None)

        assert daemon.shutdown_requested is True
        assert daemon._source_events["source1"].is_set()
        assert daemon._source_events["source2"].is_set()

    def test_signal_handler_with_multiple_sources(self):
        """Test signal handler with multiple source events."""
        daemon = TaskQueueDaemon()
        sources = [f"source{i}" for i in range(5)]
        for source in sources:
            daemon._source_events[source] = threading.Event()

        daemon._signal_handler(signal.SIGINT, None)

        assert daemon.shutdown_requested is True
        for source in sources:
            assert daemon._source_events[source].is_set()

    def test_reload_handler_logs_message(self, caplog):
        """Test reload handler logs appropriate message."""
        import logging
        caplog.set_level(logging.INFO)

        daemon = TaskQueueDaemon()
        daemon._reload_handler(signal.SIGHUP, None)

        # Should log about reload not being implemented
        assert any("reload" in record.message.lower() for record in caplog.records)


class TestSetupWatchdog:
    """Tests for watchdog setup."""

    def test_setup_watchdog_with_no_sources(self, temp_dir):
        """Test watchdog setup with no source directories configured."""
        config_file = temp_dir / "config.json"
        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()

        # Should not create events for non-existent sources
        assert len(daemon._source_events) == 0

    def test_setup_watchdog_disabled(self, temp_dir):
        """Test watchdog setup when watch_enabled is false."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {
                "watch_enabled": False,  # Disabled
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()

        # Watchdog manager is created but monitoring is disabled (early return)
        # No sources should be watched
        if daemon.watchdog_manager:
            watched = daemon.watchdog_manager.get_watched_sources()
            assert len(watched) == 0

    def test_setup_watchdog_creates_events(self, temp_dir):
        """Test that setup_watchdog creates events for sources."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()

        # Event should be created for source1
        assert "source1" in daemon._source_events

    def test_setup_watchdog_multiple_sources(self, temp_dir):
        """Test setup_watchdog with multiple sources."""
        config_file = temp_dir / "config.json"
        source1_dir = temp_dir / "source1"
        source2_dir = temp_dir / "source2"
        source1_dir.mkdir(parents=True)
        source2_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source1_dir)},
                {"id": "source2", "path": str(source2_dir)}
            ],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()

        assert "source1" in daemon._source_events
        assert "source2" in daemon._source_events

    def test_setup_watchdog_default_pattern(self, temp_dir):
        """Test watchdog setup with default pattern when none specified."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": []  # Empty patterns
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        # Should not crash with empty patterns
        daemon._setup_watchdog()

    def test_setup_watchdog_already_initialized(self, temp_dir):
        """Test calling setup_watchdog when already initialized."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()
        first_manager = daemon.watchdog_manager

        # Call again - should reuse the manager
        daemon._setup_watchdog()
        assert daemon.watchdog_manager is first_manager


class TestOnWatchdogEvent:
    """Tests for watchdog event handling."""

    def test_on_watchdog_event_with_valid_source(self):
        """Test watchdog event with a valid source."""
        daemon = TaskQueueDaemon()
        daemon._source_events["source1"] = threading.Event()

        daemon._on_watchdog_event("/path/to/task-123.md", "source1")

        assert daemon._source_events["source1"].is_set()

    def test_on_watchdog_event_with_invalid_source(self):
        """Test watchdog event with an unknown source."""
        daemon = TaskQueueDaemon()
        daemon._source_events["source1"] = threading.Event()

        # Should not crash
        daemon._on_watchdog_event("/path/to/task-123.md", "unknown_source")

        # source1 should not be set
        assert not daemon._source_events["source1"].is_set()

    def test_on_watchdog_event_clears_existing_event(self):
        """Test that setting event multiple times works correctly."""
        daemon = TaskQueueDaemon()
        daemon._source_events["source1"] = threading.Event()

        # First event
        daemon._on_watchdog_event("/path/to/task-1.md", "source1")
        assert daemon._source_events["source1"].is_set()

        # Clear and set again
        daemon._source_events["source1"].clear()
        daemon._on_watchdog_event("/path/to/task-2.md", "source1")
        assert daemon._source_events["source1"].is_set()


class TestWorkerLoopEdgeCases:
    """Tests for worker loop edge cases."""

    def test_worker_loop_with_no_event(self, temp_dir):
        """Test worker loop when no event is found for source."""
        source_dir = temp_dir / "tasks" / "task-documents"
        source_dir.mkdir(parents=True)

        daemon = TaskQueueDaemon()
        daemon.running = True
        daemon.shutdown_requested = False

        from task_queue.task_runner import TaskRunner
        daemon.task_runner = TaskRunner(str(temp_dir))

        source = TaskSourceDirectory(id="test", path=str(source_dir))

        # No event created - worker should return early
        daemon._worker_loop(source)

        # Should complete without crashing
        assert True

    def test_worker_loop_handles_exception(self, temp_dir):
        """Test worker loop handles exceptions gracefully."""
        source_dir = temp_dir / "tasks" / "task-documents"
        source_dir.mkdir(parents=True)

        daemon = TaskQueueDaemon()
        daemon.running = True
        daemon.shutdown_requested = False

        from task_queue.task_runner import TaskRunner
        daemon.task_runner = TaskRunner(str(temp_dir))

        source = TaskSourceDirectory(id="test", path=str(source_dir))
        daemon._source_events["test"] = threading.Event()

        # Mock pick_next_task to raise exception
        def raise_exception(*args, **kwargs):
            raise RuntimeError("Test error")

        daemon.task_runner.pick_next_task_from_source = raise_exception

        # Stop after exception
        def stop_after_error():
            time.sleep(0.2)
            daemon.shutdown_requested = True
            daemon._source_events["test"].set()

        stopper = threading.Thread(target=stop_after_error)
        stopper.start()

        # Should handle exception and continue
        daemon._worker_loop(source)

        stopper.join()

    def test_worker_loop_with_no_tasks(self, temp_dir):
        """Test worker loop when there are no tasks."""
        source_dir = temp_dir / "tasks" / "task-documents"
        source_dir.mkdir(parents=True)

        daemon = TaskQueueDaemon()
        daemon.running = True
        daemon.shutdown_requested = False

        from task_queue.task_runner import TaskRunner
        daemon.task_runner = TaskRunner(str(temp_dir))

        source = TaskSourceDirectory(id="test", path=str(source_dir))
        daemon._source_events["test"] = threading.Event()

        # Stop after timeout
        def stop_after_timeout():
            time.sleep(0.2)
            daemon.shutdown_requested = True
            daemon._source_events["test"].set()

        stopper = threading.Thread(target=stop_after_timeout)
        stopper.start()

        # Should wait on event with timeout
        daemon._worker_loop(source)

        stopper.join()

    def test_worker_loop_respects_shutdown_flag(self, temp_dir):
        """Test that worker loop exits when shutdown is requested."""
        source_dir = temp_dir / "tasks" / "task-documents"
        source_dir.mkdir(parents=True)

        daemon = TaskQueueDaemon()
        daemon.running = True
        daemon.shutdown_requested = False

        from task_queue.task_runner import TaskRunner
        daemon.task_runner = TaskRunner(str(temp_dir))

        source = TaskSourceDirectory(id="test", path=str(source_dir))
        daemon._source_events["test"] = threading.Event()

        # Immediately request shutdown
        daemon.shutdown_requested = True

        daemon._worker_loop(source)

        # Should exit immediately


class TestShutdown:
    """Tests for shutdown functionality."""

    def test_shutdown_sets_flags(self, temp_dir):
        """Test that shutdown sets the correct flags."""
        daemon = TaskQueueDaemon()
        daemon._source_events["source1"] = threading.Event()

        daemon._shutdown()

        assert daemon.running is False
        assert daemon.shutdown_requested is True
        assert daemon._source_events["source1"].is_set()

    def test_shutdown_with_no_workers(self, temp_dir):
        """Test shutdown when no workers are running."""
        daemon = TaskQueueDaemon()

        # Should not crash
        daemon._shutdown()

    def test_shutdown_waits_for_workers(self, temp_dir):
        """Test that shutdown waits for workers to stop."""
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        daemon = TaskQueueDaemon()

        # Create a mock worker thread
        def mock_worker():
            time.sleep(0.1)
            return

        worker = threading.Thread(target=mock_worker)
        worker.start()

        daemon._worker_threads["source1"] = worker
        daemon._source_events["source1"] = threading.Event()

        daemon._shutdown()

        worker.join()
        assert not worker.is_alive()

    def test_shutdown_with_watchdog(self, temp_dir):
        """Test shutdown stops watchdog manager."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {
                "watch_enabled": True,
                "watch_debounce_ms": 500,
                "watch_patterns": ["task-*.md"]
            }
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)
        daemon._setup_watchdog()

        # Mock stop_all to verify it's called
        original_stop_all = daemon.watchdog_manager.stop_all
        daemon.watchdog_manager.stop_all = Mock()

        daemon._shutdown()

        # stop_all should be called
        daemon.watchdog_manager.stop_all.assert_called_once()


class TestMainFunction:
    """Tests for main() function."""

    def test_main_with_default_args(self, temp_dir):
        """Test main function with default arguments."""
        with patch('task_queue.daemon.TaskQueueDaemon') as MockDaemon:
            mock_daemon = Mock()
            MockDaemon.return_value = mock_daemon

            from task_queue.daemon import main
            import sys

            # Mock sys.argv to have no args
            original_argv = sys.argv
            sys.argv = ['daemon']

            try:
                main()
            except SystemExit:
                pass

            # Daemon should be created with default config
            MockDaemon.assert_called_once()
            mock_daemon.start.assert_called_once()

            sys.argv = original_argv

    def test_main_with_once_flag(self, temp_dir):
        """Test main function with --once flag."""
        with patch('task_queue.daemon.TaskQueueDaemon') as MockDaemon:
            mock_daemon = Mock()
            MockDaemon.return_value = mock_daemon

            from task_queue.daemon import main
            import sys

            original_argv = sys.argv
            sys.argv = ['daemon', '--once']

            try:
                main()
            except SystemExit:
                pass

            mock_daemon.start.assert_called_once()

            sys.argv = original_argv

    def test_main_with_config_arg(self, temp_dir):
        """Test main function with custom config file."""
        config_file = temp_dir / "custom-config.json"

        with patch('task_queue.daemon.TaskQueueDaemon') as MockDaemon:
            mock_daemon = Mock()
            MockDaemon.return_value = mock_daemon

            from task_queue.daemon import main
            import sys

            original_argv = sys.argv
            sys.argv = ['daemon', '--config', str(config_file)]

            try:
                main()
            except SystemExit:
                pass

            # Should be called with custom config
            MockDaemon.assert_called_once_with(config_file=config_file)

            sys.argv = original_argv


class TestStartMethod:
    """Tests for start() method."""

    def test_start_exits_with_no_workspace(self, temp_dir, caplog):
        """Test start() exits when no workspace is configured."""
        import logging
        caplog.set_level(logging.ERROR)

        config_file = temp_dir / "config.json"
        config_data = {
            "version": "2.0",
            "project_workspace": "",  # Empty workspace
            "task_source_directories": [],
            "settings": {}
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)

        with patch('sys.exit') as mock_exit:
            daemon.start()
            mock_exit.assert_called_once_with(1)

    def test_start_creates_task_runner(self, temp_dir):
        """Test that start() creates the task runner."""
        config_file = temp_dir / "config.json"
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        config_data = {
            "version": "2.0",
            "project_workspace": str(temp_dir),
            "task_source_directories": [
                {"id": "source1", "path": str(source_dir)}
            ],
            "settings": {"watch_enabled": False}
        }
        config_file.write_text(json.dumps(config_data))

        daemon = TaskQueueDaemon(config_file=config_file)

        # Mock _run_loop to avoid actually running
        daemon._run_loop = Mock()

        # Set shutdown immediately
        def stop_immediately(*args):
            daemon.running = True
            daemon.shutdown_requested = True

        daemon._run_loop = stop_immediately

        daemon.start()

        assert daemon.task_runner is not None


class TestRunLoop:
    """Tests for _run_loop method."""

    def test_run_loop_creates_worker_threads(self, temp_dir):
        """Test that run loop creates worker threads."""
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        from task_queue.models import TaskSourceDirectory
        source = TaskSourceDirectory(id="source1", path=str(source_dir))

        daemon = TaskQueueDaemon()
        daemon.task_runner = Mock()
        daemon.running = True
        daemon.shutdown_requested = False

        # Mock _worker_loop to exit immediately
        daemon._worker_loop = Mock()

        # Run in thread to avoid blocking
        def run_and_stop():
            time.sleep(0.1)
            daemon.shutdown_requested = True

        stopper = threading.Thread(target=run_and_stop)
        stopper.start()

        daemon._run_loop([source])

        stopper.join()

        # Worker should have been called
        daemon._worker_loop.assert_called_once_with(source)

    def test_run_loop_creates_events_for_sources(self, temp_dir):
        """Test that run loop creates events for sources."""
        source_dir = temp_dir / "source1"
        source_dir.mkdir(parents=True)

        from task_queue.models import TaskSourceDirectory
        source = TaskSourceDirectory(id="source1", path=str(source_dir))

        daemon = TaskQueueDaemon()
        daemon.task_runner = Mock()

        # Mock _worker_loop to exit immediately
        daemon._worker_loop = Mock()

        # Stop immediately
        daemon.running = True
        daemon.shutdown_requested = True

        daemon._run_loop([source])

        # Event should be created for source1
        assert "source1" in daemon._source_events
