#!/usr/bin/env python3
"""
Test suite for results CLI with grouped commands.

Tests all new command groups:
- sources: list, add, rm
- tasks: show, logs, cancel
- workers: status, list
- status with --detailed flag
- logs command
"""

import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path

# Add task-queue to path
sys.path.insert(0, "/home/admin/workspaces/task-queue")


class TaskQueueCLITester:
    """Test suite for task-queue CLI."""

    def __init__(self):
        self.test_results = []
        self.temp_dir = None
        self.original_dir = os.getcwd()

    def setup(self):
        """Create test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix="task-queue-cli-test-")
        print(f"📁 Test directory: {self.temp_dir}")

    def teardown(self):
        """Clean up test environment."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🗑️  Cleaned up test directory")

    def run_command(self, cmd, cwd=None):
        """Run a CLI command and return result."""
        if cwd is None:
            cwd = self.temp_dir

        # Build full command
        full_cmd = [
            sys.executable, "-m", "task_monitor.cli",
            "--config", os.path.join(self.temp_dir, "test-config.json")
        ] + cmd

        result = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "/home/admin/workspaces/task-queue"}
        )

        return result

    def record_test(self, passed, message):
        """Record a test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({"passed": passed, "message": message})
        print(f"  {status}: {message}")

    def assert_returncode(self, result, expected, description=""):
        """Assert return code matches expected."""
        if result.returncode == expected:
            self.record_test(True, f"Return code {result.returncode} == {expected} {description}")
            return True
        else:
            self.record_test(False, f"Return code {result.returncode} != {expected} {description}")
            print(f"     stdout: {result.stdout[:200]}")
            print(f"     stderr: {result.stderr[:200]}")
            return False

    def assert_in_output(self, output, text, description=""):
        """Assert text is in output."""
        if text in output:
            self.record_test(True, f"Found '{text}' {description}")
            return True
        else:
            self.record_test(False, f"Missing '{text}' {description}")
            return False

    # ========================================================================
    # TESTS
    # ========================================================================

    def test_01_init_creates_structure(self):
        """Test init command creates directory structure."""
        print("\n🧪 Test 1: Init Creates Directory Structure")

        result = self.run_command(["init"])

        self.assert_returncode(result, 0, "init succeeds")
        self.assert_in_output(result.stdout, "✅ Initialization complete!", "init complete message")

        # Check directories exist
        for queue in ["ad-hoc", "planned"]:
            for subdir in ["staging", "pending", "completed", "failed", "results", "reports", "planning"]:
                dir_path = Path(self.temp_dir) / "tasks" / queue / subdir
                if dir_path.exists():
                    self.record_test(True, f"Directory exists: tasks/{queue}/{subdir}")
                else:
                    self.record_test(False, f"Directory missing: tasks/{queue}/{subdir}")

    def test_02_init_registers_sources(self):
        """Test init registers both queues."""
        print("\n🧪 Test 2: Init Registers Sources")

        result = self.run_command(["init"])

        # Check sources are registered
        result = self.run_command(["sources", "list"])

        self.assert_returncode(result, 0, "sources list succeeds")
        self.assert_in_output(result.stdout, "ad-hoc", "ad-hoc source registered")
        self.assert_in_output(result.stdout, "planned", "planned source registered")

    def test_03_status_overview(self):
        """Test status command shows overview."""
        print("\n🧪 Test 3: Status Overview")

        result = self.run_command(["status"])

        self.assert_returncode(result, 0, "status succeeds")
        self.assert_in_output(result.stdout, "📊 Task Queue Status", "status header")
        self.assert_in_output(result.stdout, "Overall Statistics", "statistics section")
        self.assert_in_output(result.stdout, "Per-Source Summary", "per-source section")

    def test_04_status_detailed(self):
        """Test status --detailed shows detailed lists."""
        print("\n🧪 Test 4: Status Detailed")

        result = self.run_command(["status", "--detailed"])

        self.assert_returncode(result, 0, "status --detailed succeeds")
        self.assert_in_output(result.stdout, "Source: ad-hoc", "shows ad-hoc source")
        self.assert_in_output(result.stdout, "Source: planned", "shows planned source")

    def test_05_sources_list_shows_running_status(self):
        """Test sources list shows running status."""
        print("\n🧪 Test 5: Sources List Shows Running Status")

        # First create some test tasks
        self._create_test_tasks()

        result = self.run_command(["sources", "list"])

        self.assert_returncode(result, 0, "sources list succeeds")
        self.assert_in_output(result.stdout, "📂 Task Source Directories", "sources header")
        # Should show ✅ for idle workers
        self.assert_in_output(result.stdout, "✅", "status indicator")

    def test_06_sources_add_custom_queue(self):
        """Test sources add can add custom queue."""
        print("\n🧪 Test 6: Sources Add Custom Queue")

        # Create custom queue directory
        custom_dir = Path(self.temp_dir) / "tasks" / "custom" / "pending"
        custom_dir.mkdir(parents=True, exist_ok=True)

        result = self.run_command([
            "sources", "add", str(custom_dir),
            "--id", "custom",
            "--project-workspace", self.temp_dir,
            "--description", "Custom test queue"
        ])

        self.assert_returncode(result, 0, "sources add succeeds")
        self.assert_in_output(result.stdout, "✅ Added Task Source Directory 'custom'", "add confirmation")

    def test_07_workers_status(self):
        """Test workers status command."""
        print("\n🧪 Test 7: Workers Status")

        result = self.run_command(["workers", "status"])

        self.assert_returncode(result, 0, "workers status succeeds")
        self.assert_in_output(result.stdout, "👷 Worker Status", "workers status header")
        self.assert_in_output(result.stdout, "Worker: ad-hoc", "shows ad-hoc worker")
        self.assert_in_output(result.stdout, "Worker: planned", "shows planned worker")
        self.assert_in_output(result.stdout, "State:", "shows worker state")

    def test_08_workers_list(self):
        """Test workers list command."""
        print("\n🧪 Test 8: Workers List")

        result = self.run_command(["workers", "list"])

        self.assert_returncode(result, 0, "workers list succeeds")
        self.assert_in_output(result.stdout, "👷 Workers:", "workers header")

    def test_09_tasks_show_without_tasks(self):
        """Test tasks show when no tasks exist."""
        print("\n🧪 Test 9: Tasks Show (No Tasks)")

        result = self.run_command(["tasks", "show", "task-20260207-123456"])

        self.assert_returncode(result, 1, "tasks show fails for non-existent task")
        self.assert_in_output(result.stdout, "❌ Task 'task-20260207-123456' not found", "error message")

    def test_10_tasks_show_with_task(self):
        """Test tasks show with actual task."""
        print("\n🧪 Test 10: Tasks Show (With Task)")

        # First initialize the system
        self.run_command(["init"])

        # Create a test task (note: task_id must match the filename without .md)
        task_file = Path(self.temp_dir) / "tasks" / "ad-hoc" / "pending" / "task-20260207-123456.md"
        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text("# Test Task\n\nThis is a test task.")

        result = self.run_command(["tasks", "show", "task-20260207-123456"])

        self.assert_returncode(result, 0, "tasks show succeeds")
        self.assert_in_output(result.stdout, "📄 Task document:", "shows task path")
        self.assert_in_output(result.stdout, "💡 Use 'cat", "shows reminder to use cat")

    def test_11_tasks_cancel_non_running(self):
        """Test tasks cancel on non-running task."""
        print("\n🧪 Test 11: Tasks Cancel Non-Running Task")

        # First initialize the system
        self.run_command(["init"])

        # Create a test task (no lock file)
        task_file = Path(self.temp_dir) / "tasks" / "ad-hoc" / "pending" / "task-20260207-999999.md"
        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text("# Test Task")

        result = self.run_command(["tasks", "cancel", "task-20260207-999999"])

        self.assert_returncode(result, 1, "tasks cancel fails for non-running task")
        self.assert_in_output(result.stdout, "not running", "error message")

    def test_12_sources_rm_removes_queue(self):
        """Test sources rm removes a queue."""
        print("\n🧪 Test 12: Sources Remove Queue")

        # First add a custom queue
        custom_dir = Path(self.temp_dir) / "tasks" / "temp" / "pending"
        custom_dir.mkdir(parents=True, exist_ok=True)

        self.run_command([
            "sources", "add", str(custom_dir),
            "--id", "temp",
            "--project-workspace", self.temp_dir
        ])

        # Now remove it
        result = self.run_command(["sources", "rm", "--source-id", "temp"])

        self.assert_returncode(result, 0, "sources rm succeeds")
        self.assert_in_output(result.stdout, "✅ Removed Task Source Directory 'temp'", "removal confirmation")

    def test_13_init_idempotent(self):
        """Test init can be run multiple times."""
        print("\n🧪 Test 13: Init Idempotent")

        # First init
        result1 = self.run_command(["init"])
        self.assert_returncode(result1, 0, "first init succeeds")

        # Second init (should detect existing)
        result2 = self.run_command(["init"])
        self.assert_returncode(result2, 0, "second init succeeds (idempotent)")
        self.assert_in_output(result2.stdout, "already initialized", "detects existing setup")

    def test_14_init_force_reinitialize(self):
        """Test init --force reinitializes."""
        print("\n🧪 Test 14: Init Force Reinitialize")

        # First init
        self.run_command(["init"])

        # Force re-init
        result = self.run_command(["init", "--force"])

        self.assert_returncode(result, 0, "init --force succeeds")
        self.assert_in_output(result.stdout, "Removed existing: ad-hoc", "removes ad-hoc")
        self.assert_in_output(result.stdout, "Removed existing: planned", "removes planned")

    def test_15_lock_file_format(self):
        """Test lock file has correct format."""
        print("\n🧪 Test 15: Lock File Format")

        # Import to test
        from task_monitor.executor import LockInfo

        # Create a test lock file
        lock_file = Path(self.temp_dir) / "test.lock"
        lock_info = LockInfo(
            task_id="task-20260207-123456",
            worker="ad-hoc",
            thread_id="140234567890123",
            pid=12345,
            started_at="2026-02-07T12:35:00.123456"
        )
        lock_info.save(lock_file)

        # Read it back
        loaded = LockInfo.from_file(lock_file)

        if loaded and loaded.task_id == lock_info.task_id:
            self.record_test(True, "Lock file saves and loads correctly")
            self.record_test(True, f"Lock has thread_id: {loaded.thread_id}")
            self.record_test(True, f"Lock has worker: {loaded.worker}")
            self.record_test(True, f"Lock has pid: {loaded.pid}")
        else:
            self.record_test(False, "Lock file format incorrect")

        # Check JSON format
        import json
        with open(lock_file, 'r') as f:
            data = json.load(f)

        if data.get("task_id") == "task-20260207-123456":
            self.record_test(True, "Lock file contains task_id")
        else:
            self.record_test(False, "Lock file missing task_id")

        if data.get("worker") == "ad-hoc":
            self.record_test(True, "Lock file contains worker")
        else:
            self.record_test(False, "Lock file missing worker")

        if "thread_id" in data:
            self.record_test(True, "Lock file contains thread_id")
        else:
            self.record_test(False, "Lock file missing thread_id")

        if "pid" in data:
            self.record_test(True, "Lock file contains pid")
        else:
            self.record_test(False, "Lock file missing pid")

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _create_test_tasks(self):
        """Create some test tasks for testing."""
        ad_hoc_dir = Path(self.temp_dir) / "tasks" / "ad-hoc" / "pending"
        planned_dir = Path(self.temp_dir) / "tasks" / "planned" / "pending"

        ad_hoc_dir.mkdir(parents=True, exist_ok=True)
        planned_dir.mkdir(parents=True, exist_ok=True)

        # Create test tasks
        (ad_hoc_dir / "task-20260207-000001.md").write_text("# Task 1\n")
        (ad_hoc_dir / "task-20260207-000002.md").write_text("# Task 2\n")
        (planned_dir / "task-20260207-000001.md").write_text("# Planned Task 1\n")

    # ========================================================================
    # RUN ALL TESTS
    # ========================================================================

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("🧪 Task Queue CLI Test Suite")
        print("=" * 60)

        try:
            self.setup()

            self.test_01_init_creates_structure()
            self.test_02_init_registers_sources()
            self.test_03_status_overview()
            self.test_04_status_detailed()
            self.test_05_sources_list_shows_running_status()
            self.test_06_sources_add_custom_queue()
            self.test_07_workers_status()
            self.test_08_workers_list()
            self.test_09_tasks_show_without_tasks()
            self.test_10_tasks_show_with_task()
            self.test_11_tasks_cancel_non_running()
            self.test_12_sources_rm_removes_queue()
            self.test_13_init_idempotent()
            self.test_14_init_force_reinitialize()
            self.test_15_lock_file_format()

            return self.print_summary()

        finally:
            self.teardown()

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("=" * 60)

        passed = sum(1 for r in self.test_results if r["passed"])
        failed = sum(1 for r in self.test_results if not r["passed"])
        total = len(self.test_results)

        print(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")

        if failed > 0:
            print("\n❌ Failed Tests:")
            for r in self.test_results:
                if not r["passed"]:
                    print(f"   - {r['message']}")

        return failed == 0


def main():
    """Run the test suite."""
    tester = TaskQueueCLITester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
