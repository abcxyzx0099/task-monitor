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
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from task_queue.models import TaskSourceDirectory
from task_queue.executor import SyncTaskExecutor


class TaskRunner:
    """
    Simplified task runner using directory-based state.

    No state file - the directory structure tells us everything.
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

    def _get_queue_dirs(self, worker: str) -> tuple[Path, Path]:
        """
        Get archive and failed directories for a specific worker/queue.

        Args:
            worker: Worker name (e.g., "ad-hoc", "planned")

        Returns:
            Tuple of (archive_dir, failed_dir)
        """
        if "ad-hoc" in worker.lower():
            base = self.project_workspace / "tasks" / "ad-hoc"
        else:
            base = self.project_workspace / "tasks" / "planned"

        return (
            base / "completed",
            base / "failed"
        )

    def pick_next_task(
        self,
        source_dirs: List[TaskSourceDirectory]
    ) -> Optional[Path]:
        """
        Pick the next task to execute from all source directories.

        Scans directories, sorts by filename (chronological order),
        and returns the first available task.

        Args:
            source_dirs: List of source directories to scan

        Returns:
            Path to task document, or None if no pending tasks
        """
        all_tasks = []

        # Scan all source directories
        for source_dir in source_dirs:
            source_path = Path(source_dir.path)
            if not source_path.exists():
                continue

            # Find all task-*.md files
            for task_file in source_path.glob("task-*.md"):
                if task_file.is_file():
                    all_tasks.append(task_file)

        # Sort by filename (chronological: task-YYYYMMDD-HHMMSS-*)
        all_tasks.sort(key=lambda p: p.name)

        # Return first available task
        if all_tasks:
            return all_tasks[0]

        return None

    def pick_next_task_from_source(
        self,
        source_dir: TaskSourceDirectory
    ) -> Optional[Path]:
        """
        Pick the next task to execute from a SINGLE source directory.

        For parallel execution: each worker thread calls this for its own source.
        Tasks are picked in chronological order (by filename).

        Args:
            source_dir: Single source directory to scan

        Returns:
            Path to task document, or None if no pending tasks in this source
        """
        source_path = Path(source_dir.path)
        if not source_path.exists():
            return None

        # Find all task-*.md files
        all_tasks = []
        for task_file in source_path.glob("task-*.md"):
            if task_file.is_file():
                all_tasks.append(task_file)

        # Sort by filename (chronological: task-YYYYMMDD-HHMMSS-*)
        all_tasks.sort(key=lambda p: p.name)

        # Return first available task
        if all_tasks:
            return all_tasks[0]

        return None

    def execute_task(self, task_file: Path, worker: str = "unknown") -> Dict:
        """
        Execute a task using the SyncTaskExecutor.

        Executes task and moves to completed/failed.

        Args:
            task_file: Path to task document
            worker: Worker name (e.g., "ad-hoc", "planned")

        Returns:
            Result dict with status and error info
        """
        task_id = task_file.stem

        # Get per-queue directories
        archive_dir, failed_dir = self._get_queue_dirs(worker)

        try:
            # Execute the task
            result = self.executor.execute(
                task_file,
                project_workspace=self.project_workspace,
                worker=worker
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

            return {
                "status": "success" if result.success else "failed",
                "task_id": task_id,
                "output": result.output,
                "error": result.error
            }

        except Exception as e:
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

    def get_status(
        self,
        source_dirs: List[TaskSourceDirectory]
    ) -> Dict:
        """
        Get current status by scanning directories.

        Args:
            source_dirs: List of source directories to scan

        Returns:
            Status dict with statistics
        """
        stats = {
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "sources": {}
        }

        for source_dir in source_dirs:
            source_path = Path(source_dir.path)
            if not source_path.exists():
                continue

            source_stats = {
                "pending": 0,
                "completed": 0,
                "failed": 0
            }

            # Count pending tasks
            for task_file in source_path.glob("task-*.md"):
                if task_file.is_file():
                    source_stats["pending"] += 1

            # Get per-queue directories for this source
            archive_dir, failed_dir = self._get_queue_dirs(source_dir.id)

            # Count completed in archive
            if archive_dir.exists():
                source_stats["completed"] = len(list(archive_dir.glob("task-*.md")))

            # Count failed
            if failed_dir.exists():
                source_stats["failed"] = len(list(failed_dir.glob("task-*.md")))

            stats["sources"][source_dir.id] = source_stats
            stats["pending"] += source_stats["pending"]
            stats["completed"] += source_stats["completed"]
            stats["failed"] += source_stats["failed"]

        return stats
