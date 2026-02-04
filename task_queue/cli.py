"""
Command-line interface for task monitor.

Provides CLI commands for managing the task monitoring system.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from task_queue.config import ConfigManager, DEFAULT_CONFIG_FILE
from task_queue.monitor import create_queue
from task_queue.models import SystemStatus


def cmd_set_project(args, config: ConfigManager) -> int:
    """Set the project path."""
    try:
        old_path = config.get_project_path()
        config.set_project_path(args.path)

        if old_path:
            print(f"✅ Project path changed: {old_path}")
            print(f"   → {args.path}")
        else:
            print(f"✅ Project path set: {args.path}")

        return 0

    except Exception as e:
        print(f"❌ Error setting project path: {e}", file=sys.stderr)
        return 1


def cmd_clear_project(args, config: ConfigManager) -> int:
    """Clear the project path."""
    old_path = config.get_project_path()
    config.clear_project_path()

    if old_path:
        print(f"✅ Project path cleared: {old_path}")
    else:
        print(f"⚠️  No project path was set")

    return 0


def cmd_show_project(args, config: ConfigManager) -> int:
    """Show current project path."""
    project_path = config.get_project_path()

    if project_path:
        print(f"📁 Project path: {project_path}")
    else:
        print(f"⚠️  No project path set")
        print()
        print(f"Set project path with:")
        print(f"  task-queue set-project <path>")

    return 0


def cmd_add_doc(args, config: ConfigManager) -> int:
    """Add a task doc directory."""
    try:
        doc_dir = config.add_task_doc_directory(
            path=args.path,
            id=args.id,
            description=args.description or ""
        )

        print(f"✅ Added task doc directory: {doc_dir.id}")
        print(f"   Path: {doc_dir.path}")
        if doc_dir.description:
            print(f"   Description: {doc_dir.description}")

        return 0

    except Exception as e:
        print(f"❌ Error adding task doc directory: {e}", file=sys.stderr)
        return 1


def cmd_remove_doc(args, config: ConfigManager) -> int:
    """Remove a task doc directory."""
    if config.remove_task_doc_directory(args.id):
        print(f"✅ Removed task doc directory: {args.id}")
        return 0
    else:
        print(f"❌ Task doc directory not found: {args.id}", file=sys.stderr)
        return 1


def cmd_list_docs(args, config: ConfigManager) -> int:
    """List task doc directories."""
    doc_dirs = config.list_task_doc_directories()

    if not doc_dirs:
        print("⚠️  No task doc directories configured")
        return 0

    print(f"\n📂 Task Doc Directories:")
    print()

    for doc_dir in doc_dirs:
        print(f"  📁 {doc_dir.id}")
        print(f"      Path: {doc_dir.path}")
        if doc_dir.description:
            print(f"      Description: {doc_dir.description}")

        # Get current status if available
        try:
            monitor = create_queue(config_file=config.config_file)
            doc_statuses = monitor.get_task_doc_directory_status()

            for doc_status in doc_statuses:
                if doc_status.id == doc_dir.id:
                    queue = doc_status.queue_stats
                    if queue:
                        print(f"      Queue: {queue}")
                    break
        except Exception:
            pass

        print()

    return 0


def cmd_status(args, config: ConfigManager) -> int:
    """Show system status."""
    try:
        monitor = create_queue(config_file=config.config_file)
        status = monitor.get_status()

        print(f"\n{'='*60}")
        print(f"📊 Task Queue Status")
        print(f"{'='*60}")

        # Running state
        running = "🟢 Running" if status.running else "🔴 Stopped"
        print(f"\nStatus: {running}")

        if status.uptime_seconds > 0:
            uptime_mins = int(status.uptime_seconds / 60)
            print(f"Uptime: {uptime_mins} minutes")

        # Load info
        if status.load_count > 0:
            print(f"Loads: {status.load_count}")
            if status.last_load_at:
                print(f"Last load: {status.last_load_at}")

        # Project
        print(f"\nProject path: {status.project_path or 'Not set'}")

        # Task doc directories
        print(f"\nTask doc directories: {status.active_task_doc_dirs}/{status.total_task_doc_dirs} active")

        # Queue stats
        print(f"\n📋 Queue Statistics:")
        print(f"   Pending:   {status.total_pending}")
        print(f"   Running:   {status.total_running}")
        print(f"   Completed: {status.total_completed}")
        print(f"   Failed:    {status.total_failed}")

        # Task doc directory details
        if args.verbose:
            print(f"\n{'='*60}")
            print(f"📂 Task Doc Directory Details")
            print(f"{'='*60}")

            for doc_status in monitor.get_task_doc_directory_status():
                print(f"\n{doc_status.id}:")
                print(f"   Path: {doc_status.path}")
                if doc_status.description:
                    print(f"   Description: {doc_status.description}")

                queue = doc_status.queue_stats
                if queue:
                    print(f"   Queue: {queue}")

        print()

        return 0

    except Exception as e:
        print(f"❌ Error getting status: {e}", file=sys.stderr)
        return 1


def cmd_queue(args, config: ConfigManager) -> int:
    """Show queue status."""
    try:
        monitor = create_queue(config_file=config.config_file)
        status = monitor.get_status()

        print(f"\nProject: {status.project_path or 'Not set'}")
        print(f"Task doc directories: {status.active_task_doc_dirs}/{status.total_task_doc_dirs} active")

        print(f"\n📋 Queue Statistics:")
        print(f"   Pending:   {status.total_pending}")
        print(f"   Running:   {status.total_running}")
        print(f"   Completed: {status.total_completed}")
        print(f"   Failed:    {status.total_failed}")

        # Show task doc directory breakdown
        for doc_status in monitor.get_task_doc_directory_status():
            queue = doc_status.queue_stats
            pending = queue.get("pending", 0)
            running = queue.get("running", 0)
            completed = queue.get("completed", 0)
            failed = queue.get("failed", 0)

            if pending + running + completed + failed > 0:
                print(f"\n{doc_status.id}:")
                print(f"   Pending: {pending}, Running: {running}, Completed: {completed}, Failed: {failed}")

        print()

        return 0

    except Exception as e:
        print(f"❌ Error getting queue: {e}", file=sys.stderr)
        return 1


def cmd_load(args, config: ConfigManager) -> int:
    """Load tasks from task doc directories."""
    try:
        monitor = create_queue(config_file=config.config_file)

        print(f"\n📂 Loading tasks...")

        results = monitor.load_tasks()

        total = results.get("total", 0)
        if total > 0:
            print(f"\n✅ Loaded {total} new tasks")
        else:
            print(f"\n📭 No new tasks found")

        return 0

    except Exception as e:
        print(f"❌ Error loading tasks: {e}", file=sys.stderr)
        return 1


def cmd_process(args, config: ConfigManager) -> int:
    """Trigger immediate processing."""
    try:
        monitor = create_queue(config_file=config.config_file)

        result = monitor.process_tasks(max_tasks=args.max_tasks)

        status = result.get("status", "unknown")

        print()

        if status == "completed":
            processed = result.get("processed", 0)
            failed = result.get("failed", 0)
            remaining = result.get("remaining", 0)

            print(f"📊 Processing Summary:")
            print(f"   ✅ Completed: {processed}")
            print(f"   ❌ Failed: {failed}")
            print(f"   📋 Remaining: {remaining}")

        elif status == "empty":
            print(f"📭 No pending tasks to process")

        elif status == "skipped":
            reason = result.get("reason", "unknown")
            print(f"⏸️  Skipped: {reason}")

        print()

        return 0

    except Exception as e:
        print(f"❌ Error processing: {e}", file=sys.stderr)
        return 1


def cmd_run(args, config: ConfigManager) -> int:
    """Run monitor interactively."""
    try:
        monitor = create_queue(config_file=config.config_file)

        cycles = args.cycles if args.cycles > 0 else None

        monitor.run(cycles=cycles)

        return 0

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="task-queue",
        description="Task monitoring system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set project path
  task-queue set-project /path/to/project

  # Add task doc directory
  task-queue add-doc /path/to/docs --id main

  # List task doc directories
  task-queue list-docs

  # Load tasks
  task-queue load

  # Process tasks
  task-queue process

  # Show status
  task-queue status
        """
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to configuration file"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Project commands
    project_parser = subparsers.add_parser("set-project", help="Set project path")
    project_parser.add_argument("path", help="Path to project root")

    subparsers.add_parser("clear-project", help="Clear project path")
    subparsers.add_parser("show-project", help="Show current project path")

    # Task doc directory commands
    doc_parser = subparsers.add_parser("add-doc", help="Add task doc directory")
    doc_parser.add_argument("path", help="Path to task doc directory")
    doc_parser.add_argument("--id", required=True, help="Unique identifier")
    doc_parser.add_argument("--description", default="", help="Description")

    remove_doc_parser = subparsers.add_parser("remove-doc", help="Remove task doc directory")
    remove_doc_parser.add_argument("id", help="Task doc directory ID")

    list_docs_parser = subparsers.add_parser("list-docs", help="List task doc directories")

    # Status and queue
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed status")

    subparsers.add_parser("queue", help="Show queue status")

    # Load and process
    subparsers.add_parser("load", help="Load tasks from task doc directories")

    process_parser = subparsers.add_parser("process", help="Process pending tasks")
    process_parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Max tasks to process"
    )

    # Run
    run_parser = subparsers.add_parser("run", help="Run monitor interactively")
    run_parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of cycles (0 = infinite)"
    )

    return parser


def main() -> int:
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Load config
    config = ConfigManager(args.config)

    # Dispatch command
    handlers = {
        ("set-project",): cmd_set_project,
        ("clear-project",): cmd_clear_project,
        ("show-project",): cmd_show_project,
        ("add-doc",): cmd_add_doc,
        ("remove-doc",): cmd_remove_doc,
        ("list-docs",): cmd_list_docs,
        ("status",): cmd_status,
        ("queue",): cmd_queue,
        ("load",): cmd_load,
        ("process",): cmd_process,
        ("run",): cmd_run,
    }

    key = (args.command,)

    handler = handlers.get(key)

    if handler:
        return handler(args, config)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
