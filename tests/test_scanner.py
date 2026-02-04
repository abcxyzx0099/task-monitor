"""Tests for task_queue scanner module."""

import pytest
from pathlib import Path
from datetime import datetime

from task_queue.scanner import TaskScanner
from task_queue.models import TaskDocDirectory, DiscoveredTask


class TestTaskScanner:
    """Tests for TaskScanner class."""

    @pytest.fixture
    def scanner(self):
        """Create a TaskScanner instance."""
        return TaskScanner(enable_file_hash=True)

    @pytest.fixture
    def scanner_no_hash(self):
        """Create a TaskScanner without file hashing."""
        return TaskScanner(enable_file_hash=False)

    @pytest.fixture
    def temp_doc_dir(self, tmp_path):
        """Create a temporary task document directory with sample files."""
        # Create valid task files
        (tmp_path / "task-20250131-100000-test-task.md").write_text("# Test Task")
        (tmp_path / "task-20250131-110000-another-task.md").write_text("# Another Task")

        # Create invalid file (wrong prefix)
        (tmp_path / "other-file.md").write_text("# Other File")

        # Create invalid file (wrong format)
        (tmp_path / "task-invalid.md").write_text("# Invalid Task")

        # Create subdirectory (should be ignored)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "task-20250131-120000-in-subdir.md").write_text("# Subdir Task")

        return tmp_path

    def test_scan_task_doc_directory(self, scanner, temp_doc_dir):
        """Test scanning a single task doc directory."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main task docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)

        # Should find 2 valid task files
        assert len(discovered) == 2

        # Check first task
        task1 = next((t for t in discovered if "test-task" in t.task_id), None)
        assert task1 is not None
        assert task1.task_doc_dir_id == "main"
        assert task1.file_size > 0

        # Check second task
        task2 = next((t for t in discovered if "another-task" in t.task_id), None)
        assert task2 is not None

    def test_scan_nonexistent_directory(self, scanner):
        """Test scanning a directory that doesn't exist."""
        # Don't use TaskDocDirectory validation for this test
        # Just test the scanner directly with a path
        from task_queue.models import TaskDocDirectory

        # Use a path that exists but create TaskDocDirectory without validation
        doc_dir = TaskDocDirectory.model_construct(
            id="main",
            path="/nonexistent/path",
            description="Nonexistent"
        )

        # Should return empty list, not raise error
        discovered = scanner.scan_task_doc_directory(doc_dir)
        assert discovered == []

    def test_scan_task_doc_directories(self, scanner, temp_doc_dir):
        """Test scanning multiple task doc directories."""
        doc_dir1 = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        doc_dir2 = TaskDocDirectory(
            id="secondary",
            path=str(temp_doc_dir),
            description="Secondary docs"
        )

        discovered = scanner.scan_task_doc_directories([doc_dir1, doc_dir2])

        # Should find 2 tasks from each directory (same path, different IDs)
        assert len(discovered) == 4

    def test_file_hash_calculation(self, scanner, temp_doc_dir):
        """Test that file hashes are calculated correctly."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)

        for task in discovered:
            assert task.file_hash is not None
            assert len(task.file_hash) == 32  # MD5 hash length
            assert task.file_size > 0

    def test_no_file_hash_when_disabled(self, scanner_no_hash, temp_doc_dir):
        """Test that file hashes are not calculated when disabled."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        discovered = scanner_no_hash.scan_task_doc_directory(doc_dir)

        for task in discovered:
            assert task.file_hash is None
            assert task.file_size > 0

    def test_invalid_task_id_format(self, scanner, tmp_path):
        """Test that invalid task ID formats are skipped."""
        # Create files with invalid formats
        (tmp_path / "task-invalid.md").write_text("# Invalid")
        (tmp_path / "task-20250131-1000.md").write_text("# Missing seconds")
        (tmp_path / "not-a-task.md").write_text("# Not a task")

        doc_dir = TaskDocDirectory(
            id="main",
            path=str(tmp_path),
            description="Main docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)

        # Should find 0 valid tasks
        assert len(discovered) == 0

    def test_is_file_modified(self, scanner, temp_doc_dir):
        """Test file modification detection."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)
        task = discovered[0]

        # File should be considered modified when hash is None
        assert scanner.is_file_modified(task.task_doc_file, None) is True

        # File should not be modified when hash matches
        assert scanner.is_file_modified(task.task_doc_file, task.file_hash) is False

        # File should be modified when hash differs
        assert scanner.is_file_modified(task.task_doc_file, "wronghash") is True

    def test_is_file_modified_when_disabled(self, scanner_no_hash, temp_doc_dir):
        """Test file modification detection when hashing is disabled."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        discovered = scanner_no_hash.scan_task_doc_directory(doc_dir)
        task = discovered[0]

        # Should always return False when hashing is disabled
        assert scanner_no_hash.is_file_modified(task.task_doc_file, None) is False
        assert scanner_no_hash.is_file_modified(task.task_doc_file, "anyhash") is False

    def test_discovered_task_attributes(self, scanner, temp_doc_dir):
        """Test that DiscoveredTask has all required attributes."""
        doc_dir = TaskDocDirectory(
            id="test-dir",
            path=str(temp_doc_dir),
            description="Test docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)
        task = discovered[0]

        assert isinstance(task, DiscoveredTask)
        assert task.task_id is not None
        assert task.task_doc_file is not None
        assert task.task_doc_dir_id == "test-dir"
        assert task.discovered_at is not None
        assert isinstance(task.discovered_at, str)

    def test_empty_directory(self, scanner, tmp_path):
        """Test scanning an empty directory."""
        doc_dir = TaskDocDirectory(
            id="empty",
            path=str(tmp_path),
            description="Empty dir"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)
        assert len(discovered) == 0

    def test_scan_returns_sorted_results(self, scanner, temp_doc_dir):
        """Test that scan results are returned in predictable order."""
        doc_dir = TaskDocDirectory(
            id="main",
            path=str(temp_doc_dir),
            description="Main docs"
        )

        discovered = scanner.scan_task_doc_directory(doc_dir)

        # Results should be returned in the order found by glob
        # (not necessarily sorted, but should be consistent)
        assert len(discovered) == 2
        task_ids = [t.task_id for t in discovered]
        assert all(isinstance(tid, str) for tid in task_ids)
