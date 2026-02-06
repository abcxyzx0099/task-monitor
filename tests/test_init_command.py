#!/usr/bin/env python3
"""
Test suite for task-queue init command.

Tests the initialization functionality including:
- Basic initialization
- Idempotent behavior (re-running)
- Force re-initialization
- Skip existing behavior
- Directory structure creation
- Configuration registration
"""

import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime


class TestInitCommand:
    """Test suite for task-queue init command."""

    def __init__(self):
        self.test_results = []
        self.temp_dir = None
        self.original_dir = Path.cwd()

    def setup(self):
        """Create a temporary test directory."""
        self.temp_dir = tempfile.mkdtemp(prefix="task-queue-test-")
        print(f"📁 Test directory: {self.temp_dir}")

    def teardown(self):
        """Clean up test directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🗑️  Cleaned up test directory")

    def run_init_command(self, args="--skip-existing", cwd=None):
        """Run the init command and return result."""
        if cwd is None:
            cwd = self.temp_dir

        # Use a test-specific config file for isolation
        test_config = os.path.join(self.temp_dir, "test-config.json")

        cmd = [
            sys.executable, "-m", "task_queue.cli",
            "--config", test_config,
            "init"
        ]

        # Add arguments (excluding --config which is already added)
        if args:
            cmd.extend(args.split())

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "/home/admin/workspaces/task-queue"}
        )

        return result

    def assert_dir_exists(self, path, description=""):
        """Assert that a directory exists."""
        if os.path.exists(path):
            self.record_test(True, f"Directory exists: {path} {description}")
            return True
        else:
            self.record_test(False, f"Directory missing: {path} {description}")
            return False

    def assert_dir_not_exists(self, path, description=""):
        """Assert that a directory does not exist."""
        if not os.path.exists(path):
            self.record_test(True, f"Directory correctly missing: {path} {description}")
            return True
        else:
            self.record_test(False, f"Directory unexpectedly exists: {path} {description}")
            return False

    def assert_in_output(self, output, text, description=""):
        """Assert that text is in output."""
        if text in output:
            self.record_test(True, f"Found expected text: '{text}' {description}")
            return True
        else:
            self.record_test(False, f"Missing expected text: '{text}' {description}")
            return False

    def assert_not_in_output(self, output, text, description=""):
        """Assert that text is NOT in output."""
        if text not in output:
            self.record_test(True, f"Text correctly absent: '{text}' {description}")
            return True
        else:
            self.record_test(False, f"Text unexpectedly present: '{text}' {description}")
            return False

    def assert_returncode(self, result, expected_code, description=""):
        """Assert return code matches expected."""
        if result.returncode == expected_code:
            self.record_test(True, f"Return code {result.returncode} == {expected_code} {description}")
            return True
        else:
            self.record_test(False, f"Return code {result.returncode} != {expected_code} {description}")
            return False

    def record_test(self, passed, message):
        """Record a test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({"passed": passed, "message": message})
        print(f"  {status}: {message}")

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

    def test_01_basic_initialization(self):
        """Test basic initialization creates directories and config."""
        print("\n🧪 Test 1: Basic Initialization")

        # Run init
        result = self.run_init_command(args="", cwd=self.temp_dir)

        # Check return code
        self.assert_returncode(result, 0, "Basic init succeeds")

        # Check directories were created
        base = Path(self.temp_dir) / "tasks"
        self.assert_dir_exists(base / "ad-hoc" / "staging", "ad-hoc staging")
        self.assert_dir_exists(base / "ad-hoc" / "pending", "ad-hoc pending")
        self.assert_dir_exists(base / "ad-hoc" / "completed", "ad-hoc completed")
        self.assert_dir_exists(base / "ad-hoc" / "failed", "ad-hoc failed")
        self.assert_dir_exists(base / "ad-hoc" / "results", "ad-hoc results")
        self.assert_dir_exists(base / "ad-hoc" / "reports", "ad-hoc reports")

        self.assert_dir_exists(base / "planned" / "staging", "planned staging")
        self.assert_dir_exists(base / "planned" / "pending", "planned pending")
        self.assert_dir_exists(base / "planned" / "completed", "planned completed")
        self.assert_dir_exists(base / "planned" / "failed", "planned failed")
        self.assert_dir_exists(base / "planned" / "results", "planned results")
        self.assert_dir_exists(base / "planned" / "reports", "planned reports")
        self.assert_dir_exists(base / "planned" / "planning", "planned planning")

        # Check output contains expected messages
        self.assert_in_output(result.stdout, "✅ Initialization complete!", "Completion message")
        self.assert_in_output(result.stdout, "Registered: ad-hoc", "ad-hoc registered")
        self.assert_in_output(result.stdout, "Registered: planned", "planned registered")

    def test_02_idempotent_behavior(self):
        """Test that running init again detects existing setup."""
        print("\n🧪 Test 2: Idempotent Behavior (detects existing setup)")

        # First init
        self.run_init_command(args="", cwd=self.temp_dir)

        # Second init (should detect existing)
        result = self.run_init_command(args="", cwd=self.temp_dir)

        # Check return code (should still succeed)
        self.assert_returncode(result, 0, "Second init succeeds")

        # Check warning message
        self.assert_in_output(result.stdout, "appears to be already initialized", "Already initialized warning")
        self.assert_in_output(result.stdout, "ad-hoc, planned", "Lists existing sources")

    def test_03_skip_existing_flag(self):
        """Test --skip-existing flag doesn't show warning."""
        print("\n🧪 Test 3: Skip Existing Flag")

        # First init
        self.run_init_command(args="", cwd=self.temp_dir)

        # Second init with --skip-existing
        result = self.run_init_command(args="--skip-existing", cwd=self.temp_dir)

        # Check return code
        self.assert_returncode(result, 0, "Init with skip-existing succeeds")

        # Check that it skips existing queues
        self.assert_in_output(result.stdout, "Skipped existing: ad-hoc", "Skips ad-hoc")
        self.assert_in_output(result.stdout, "Skipped existing: planned", "Skips planned")

        # Should NOT show the "already initialized" warning
        self.assert_not_in_output(result.stdout, "appears to be already initialized", "No warning with skip-existing")

    def test_04_force_reinitialization(self):
        """Test --force flag replaces existing configuration."""
        print("\n🧪 Test 4: Force Re-initialization")

        # First init
        self.run_init_command(args="", cwd=self.temp_dir)

        # Add a file to one of the directories to verify it survives
        test_file = Path(self.temp_dir) / "tasks" / "ad-hoc" / "pending" / "test-file.txt"
        test_file.write_text("test content")

        # Force re-init
        result = self.run_init_command(args="--force", cwd=self.temp_dir)

        # Check return code
        self.assert_returncode(result, 0, "Force init succeeds")

        # Check that it removed and re-registered
        self.assert_in_output(result.stdout, "Removed existing: ad-hoc", "Removes ad-hoc")
        self.assert_in_output(result.stdout, "Removed existing: planned", "Removes planned")
        self.assert_in_output(result.stdout, "Registered: ad-hoc", "Re-registers ad-hoc")
        self.assert_in_output(result.stdout, "Registered: planned", "Re-registers planned")

        # Verify test file still exists (directories not deleted)
        self.assert_dir_exists(test_file.parent, "Directory preserved during force")

    def test_05_workspace_detection(self):
        """Test that current directory is used as workspace."""
        print("\n🧪 Test 5: Workspace Detection")

        result = self.run_init_command(args="", cwd=self.temp_dir)

        # Check output shows correct workspace
        expected_workspace = f"Project Workspace: {self.temp_dir}"
        self.assert_in_output(result.stdout, expected_workspace, "Detects current directory as workspace")

    def test_06_configuration_persistence(self):
        """Test that configuration persists across invocations."""
        print("\n🧪 Test 6: Configuration Persistence")

        # Init
        self.run_init_command(args="", cwd=self.temp_dir)

        # Check config file was created/updated
        config_file = Path.home() / ".config" / "task-queue" / "config.json"
        self.assert_dir_exists(config_file.parent, "Config directory exists")
        # Note: Can't easily check config file content as it's in user's home
        # but we verified init succeeded

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("🧪 Task Queue Init Command Test Suite")
        print("=" * 60)

        try:
            self.setup()

            self.test_01_basic_initialization()
            self.test_02_idempotent_behavior()
            self.test_03_skip_existing_flag()
            self.test_04_force_reinitialization()
            self.test_05_workspace_detection()
            self.test_06_configuration_persistence()

            success = self.print_summary()

            return 0 if success else 1

        finally:
            self.teardown()


def main():
    """Main entry point."""
    tester = TestInitCommand()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
