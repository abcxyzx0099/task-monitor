"""
Task Runner for directory-based state architecture.

No state file - directory structure is the source of truth:
- tasks/ad-hoc/pending/       - pending ad-hoc tasks
- tasks/ad-hoc/completed/     - completed ad-hoc tasks
- tasks/ad-hoc/failed/        - failed ad-hoc tasks
- tasks/planned/pending/      - pending planned tasks
- tasks/planned/completed/    - completed planned tasks
- tasks/planned/failed/       - failed planned tasks
"""

import os
import shutil
import socket
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from task_monitor.models import Queue
from task_monitor.executor import SyncTaskExecutor


logger = logging.getLogger(__name__)


class TaskRunner:
    """
    Simplified task runner using directory-based state.

    No state file - the directory structure tells us everything.
    Uses in-memory tracking for currently running tasks.
    Uses file-based status tracking (.running files) for CLI visibility.
    """

    def __init__(
        self,
        project_workspace: str
    ):
        """
        Initialize task runner.

        Args:
            project_workspace: Path to project workspace (used as cwd for SDK execution)
        """
        self.project_workspace = Path(project_workspace).resolve()

        # Executor for running tasks
        self.executor = SyncTaskExecutor()

        # In-memory tracking: which task is currently running per queue
        self.current_tasks = {}  # queue_id -> task_id

    def _get_queue_dirs(self, queue: Queue) -> tuple[Path, Path]:
        """
        Get archive and failed directories for a specific queue.

        Args:
            queue: Queue configuration

        Returns:
            Tuple of (completed_dir, failed_dir)
        """
        # The queue path is: .../tasks/{queue}/
        # Subdirectories are: pending/, completed/, failed/, results/
        queue_path = Path(queue.path)

        return (
            queue_path / "completed",
            queue_path / "failed"
        )

    def pick_next_task(
        self,
        queues: List[Queue]
    ) -> Optional[Path]:
        """
        Pick the next task to execute from all queues.

        Scans directories, sorts by filename (chronological order),
        and returns the first available task.

        Args:
            queues: List of queues to scan

        Returns:
            Path to task document, or None if no pending tasks
        """
        all_tasks = []

        # Scan all queue pending directories
        for queue in queues:
            pending_path = Path(queue.path) / "pending"
            if not pending_path.exists():
                continue

            # Find all task-*.md files
            for task_file in pending_path.glob("task-*.md"):
                if task_file.is_file():
                    all_tasks.append(task_file)

        # Sort by filename (chronological: task-YYYYMMDD-HHMMSS-*)
        all_tasks.sort(key=lambda p: p.name)

        # Return first available task
        if all_tasks:
            return all_tasks[0]

        return None

    def pick_next_task_from_queue(
        self,
        queue: Queue
    ) -> Optional[Path]:
        """
        Pick the next task to execute from a SINGLE queue.

        For parallel execution: each worker thread calls this for its own queue.
        Tasks are picked in chronological order (by filename).

        Args:
            queue: Queue configuration

        Returns:
            Path to task document, or None if no pending tasks in this queue
        """
        pending_path = Path(queue.path) / "pending"
        if not pending_path.exists():
            return None

        # Find all task-*.md files
        all_tasks = []
        for task_file in pending_path.glob("task-*.md"):
            if task_file.is_file():
                all_tasks.append(task_file)

        # Sort by filename (chronological: task-YYYYMMDD-HHMMSS-*)
        all_tasks.sort(key=lambda p: p.name)

        # Return first available task
        if all_tasks:
            return all_tasks[0]

        return None

    def execute_task(self, task_file: Path, queue: Queue) -> Dict:
        """
        Execute a task using the SyncTaskExecutor.

        Executes task and moves to completed/failed.
        Uses in-memory tracking for currently running task.
        Uses file-based status tracking for CLI visibility.

        Args:
            task_file: Path to task document
            queue: Queue configuration

        Returns:
            Result dict with status and error info
        """
        task_id = task_file.stem

        # Set in-memory tracking
        self.current_tasks[queue.id] = task_id

        # Write .running status file for CLI visibility
        queue_path = Path(queue.path)
        running_file = queue_path / f".{queue.id}.running"
        try:
            running_file.write_text(task_id)
        except OSError as e:
            logger.warning(f"Failed to write running status file: {e}")

        # Get per-queue directories
        archive_dir, failed_dir = self._get_queue_dirs(queue)

        try:
            # Execute the task
            result = self.executor.execute(
                task_file,
                project_workspace=self.project_workspace,
                worker=queue.id
            )

            # Task completed - handle result
            if result.success:
                # Move to completed
                try:
                    shutil.move(str(task_file), str(archive_dir / task_file.name))
                except OSError as e:
                    return {
                        "status": "warning",
                        "error": f"Task completed but failed to archive: {e}",
                        "task_id": task_id
                    }
            else:
                # Move to failed directory
                try:
                    failed_file = failed_dir / task_file.name
                    shutil.move(str(task_file), str(failed_file))

                    # Add error info to task document
                    error_file = failed_file.with_suffix(f".error.{uuid.uuid4().hex[:8]}")
                    error_file.write_text(f"Error: {result.error}\n")
                except OSError as e:
                    return {
                        "status": "warning",
                        "error": f"Task failed but failed to move: {e}",
                        "task_id": task_id
                    }

            # Clear in-memory tracking
            self.current_tasks.pop(queue.id, None)

            # Remove .running status file
            try:
                running_file.unlink(missing_ok=True)
            except OSError:
                pass

            return {
                "status": "success" if result.success else "failed",
                "task_id": task_id,
                "output": result.output,
                "error": result.error
            }

        except Exception as e:
            # Clear in-memory tracking on exception
            self.current_tasks.pop(queue.id, None)

            # Remove .running status file on exception
            try:
                running_file.unlink(missing_ok=True)
            except OSError:
                pass

            # Exception during execution
            try:
                # Move to failed directory
                failed_file = failed_dir / task_file.name
                shutil.move(str(task_file), str(failed_file))
            except OSError:
                pass

            return {
                "status": "error",
                "error": str(e),
                "task_id": task_id
            }

    def get_current_task(self, queue_id: str, queue_path: Optional[Path] = None) -> Optional[str]:
        """
        Get the currently running task for a queue.

        Reads from the .running status file for CLI visibility.
        Falls back to in-memory tracking for daemon process.

        Args:
            queue_id: Queue identifier (e.g., "ad-hoc", "planned")
            queue_path: Optional path to queue directory (for CLI context)

        Returns:
            Task ID if a task is running, None otherwise
        """
        # Try file-based tracking first (works for both CLI and daemon)
        if queue_path:
            running_file = queue_path / f".{queue_id}.running"
            if running_file.exists():
                try:
                    return running_file.read_text().strip()
                except OSError:
                    pass

        # Fall back to in-memory tracking (daemon only)
        return self.current_tasks.get(queue_id)

    def get_status(
        self,
        queues: List[Queue]
    ) -> Dict:
        """
        Get current status by scanning directories.

        Args:
            queues: List of queues to scan

        Returns:
            Status dict with statistics
        """
        stats = {
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "queues": {}
        }

        for queue in queues:
            pending_path = Path(queue.path) / "pending"
            if not pending_path.exists():
                continue

            queue_stats = {
                "pending": 0,
                "completed": 0,
                "failed": 0
            }

            # Count pending tasks
            for task_file in pending_path.glob("task-*.md"):
                if task_file.is_file():
                    queue_stats["pending"] += 1

            # Get per-queue directories for this queue
            archive_dir, failed_dir = self._get_queue_dirs(queue)

            # Count completed in archive
            if archive_dir.exists():
                queue_stats["completed"] = len(list(archive_dir.glob("task-*.md")))

            # Count failed
            if failed_dir.exists():
                queue_stats["failed"] = len(list(failed_dir.glob("task-*.md")))

            stats["queues"][queue.id] = queue_stats
            stats["pending"] += queue_stats["pending"]
            stats["completed"] += queue_stats["completed"]
            stats["failed"] += queue_stats["failed"]

        return stats
