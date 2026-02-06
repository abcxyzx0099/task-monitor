"""
Command-line interface for task-queue (Directory-Based State).

Simplified CLI - no state file operations.
"""

import sys
import argparse
import subprocess
from pathlib import Path

from task_queue.config import ConfigManager, DEFAULT_CONFIG_FILE
from task_queue.task_runner import TaskRunner


def _restart_daemon() -> bool:
    """Restart the task-queue daemon service."""
    try:
        print("🔄 Restarting daemon to apply changes...")
        result = subprocess.run(
            ["systemctl", "--user", "restart", "task-queue.service"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Daemon restarted successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Failed to restart daemon: {e}")
        if e.stderr:
            print(f"   Error output: {e.stderr.strip()}")
        print("   Please restart manually: systemctl --user restart task-queue.service")
        return False
    except Exception as e:
        print(f"⚠️  Failed to restart daemon: {e}")
        print("   Please restart manually: systemctl --user restart task-queue.service")
        return False


def cmd_init(args):
    """Initialize task system from current directory.

    Creates directory structure and registers both ad-hoc and planned queues.
    Uses current directory as project workspace.
    """
    import os
    from datetime import datetime

    # Get current directory as project workspace
    project_workspace = Path.cwd()
    print("=" * 60)
    print("🚀 Task System Initialization")
    print("=" * 60)
    print(f"\n📁 Project Workspace: {project_workspace}")

    # Define queue configurations
    queues = [
        {
            "id": "ad-hoc",
            "path": project_workspace / "tasks" / "ad-hoc" / "task-documents",
            "description": "Quick, spontaneous tasks from conversation",
            "subdirs": ["task-staging", "task-documents", "task-archive", "task-failed", "task-queue", "task-reports"]
        },
        {
            "id": "planned",
            "path": project_workspace / "tasks" / "planned" / "task-documents",
            "description": "Organized, sequential tasks from planning docs",
            "subdirs": ["task-staging", "task-documents", "task-archive", "task-failed", "task-queue", "task-reports"]
        }
    ]

    config_manager = ConfigManager(args.config)

    # Check if already initialized (only warn if not using force or skip-existing)
    existing_sources = [s.id for s in config_manager.config.task_source_directories]
    already_initialized = "ad-hoc" in existing_sources or "planned" in existing_sources

    if already_initialized and not args.force and not args.skip_existing:
        print("\n⚠️  Task system appears to be already initialized.")
        print("   Found sources:", ", ".join(existing_sources))
        print("\nUse --force to re-initialize or --skip-existing to add missing queues only.")
        return 0

    # Create directory structure and register queues
    print("\n📂 Creating directory structure...")

    for queue in queues:
        queue_base = queue["path"].parent

        # Create subdirectories
        for subdir in queue["subdirs"]:
            subdir_path = queue_base / subdir
            try:
                subdir_path.mkdir(parents=True, exist_ok=True)
                print(f"   ✅ Created: {subdir_path.relative_to(project_workspace)}")
            except Exception as e:
                print(f"   ❌ Failed to create {subdir_path}: {e}")
                return 1

    print("\n📋 Registering Task Source Directories...")

    # Set project workspace
    if not config_manager.config.project_workspace:
        config_manager.set_project_workspace(str(project_workspace))
        print(f"   ✅ Set Project Workspace: {project_workspace}")

    # Register queues
    for queue in queues:
        source_id = queue["id"]
        task_source_dir = str(queue["path"])

        # Skip if already exists and --skip-existing is set
        if args.skip_existing and config_manager.config.get_task_source_directory(source_id):
            print(f"   ⏭️  Skipped existing: {source_id}")
            continue

        try:
            # Remove existing if force mode
            if args.force and config_manager.config.get_task_source_directory(source_id):
                config_manager.config.remove_task_source_directory(source_id)
                print(f"   🔄 Removed existing: {source_id}")

            # Add source directory
            config_manager.add_task_source_directory(
                path=task_source_dir,
                id=source_id,
                description=queue["description"]
            )
            print(f"   ✅ Registered: {source_id}")
            print(f"      Path: {task_source_dir}")
        except Exception as e:
            print(f"   ❌ Failed to register {source_id}: {e}")
            return 1

    # Save configuration
    try:
        config_manager.save_config()
        print("\n💾 Configuration saved")
    except Exception as e:
        print(f"\n❌ Failed to save configuration: {e}")
        return 1

    # Verification
    print("\n🔍 Verifying setup...")

    # Reload config to verify
    config_manager = ConfigManager(args.config)
    registered = config_manager.config.task_source_directories
    registered_ids = [s.id for s in registered]

    print(f"\n✅ Initialization complete!")
    print(f"\n📊 Summary:")
    print(f"   Project Workspace: {project_workspace}")
    print(f"   Registered Queues: {len(registered)}")

    for source in registered:
        print(f"\n   📁 {source.id}")
        print(f"      Path: {source.path}")
        if source.description:
            print(f"      Description: {source.description}")

    # Show next steps
    print(f"\n📚 Next Steps:")
    print(f"   1. Create tasks using the task-documents skill")
    print(f"   2. Start daemon: systemctl --user start task-queue.service")
    print(f"   3. Check status: python -m task_queue.cli status")
    print(f"   4. View logs: journalctl --user -u task-queue.service -f")

    # Offer to restart daemon
    if args.restart_daemon:
        _restart_daemon()

    return 0


def cmd_status(args):
    """Show system status."""
    try:
        config_manager = ConfigManager(args.config)
        config = config_manager.config
    except Exception as e:
        print(f"❌ Error loading configuration: {e}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("📊 Task Queue Status")
    print("=" * 60)

    # Configuration info
    print(f"\nConfiguration: {args.config}")
    print(f"Project Workspace: {config.project_workspace or 'Not set'}")

    # Create task runner to get status
    if not config.project_workspace:
        print("\n⚠️  No Project Workspace set")
        print("Use 'task-queue register' to set up the workspace")
        return 0

    task_runner = TaskRunner(
        project_workspace=config.project_workspace
    )

    source_dirs = config.task_source_directories

    if not source_dirs:
        print("\n⚠️  No Task Source Directories configured")
        print("Use 'task-queue register' to add a source directory")
        print("Use 'task-queue unregister --source-id <id>' to remove a source directory")
        return 0

    print(f"\nTask Source Directories: {len(source_dirs)}")

    # Get status by scanning directories
    status = task_runner.get_status(source_dirs)

    print(f"\n📋 Overall Statistics:")
    print(f"   Pending:   {status['pending']}")
    print(f"   Completed: {status['completed']}")
    print(f"   Failed:    {status['failed']}")

    # Per-source breakdown
    print(f"\n📁 Per-Source Details:")
    for source_id, source_stats in status['sources'].items():
        source_dir = config.get_task_source_directory(source_id)
        print(f"\n  📁 {source_id}")
        if source_dir:
            print(f"      Path: {source_dir.path}")
            print(f"      Description: {source_dir.description}")
        print(f"      Pending: {source_stats['pending']}, "
              f"Completed: {source_stats['completed']}, Failed: {source_stats['failed']}")

    return 0


def cmd_register(args):
    """Register a Task Source Directory for watchdog monitoring."""
    try:
        config_manager = ConfigManager(args.config)

        # Set project workspace if not set
        if not config_manager.config.project_workspace:
            config_manager.set_project_workspace(args.project_workspace)

        # Add source directory
        source_dir = config_manager.add_task_source_directory(
            path=args.task_source_dir,
            id=args.source_id
        )

        # Save config
        config_manager.save_config()

        print(f"\n✅ Registered Task Source Directory '{args.source_id}'")
        print(f"   Path: {args.task_source_dir}")
        print(f"   Workspace: {args.project_workspace}")

        # Count existing tasks
        from pathlib import Path
        source_path = Path(args.task_source_dir)
        task_files = list(source_path.glob("task-*.md"))

        if task_files:
            print(f"\n📋 Found {len(task_files)} task documents in directory")
        else:
            print(f"\n📭 No task documents found yet")

        # Restart daemon to apply changes
        _restart_daemon()

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_list_sources(args):
    """List Task Source Directories."""
    try:
        config_manager = ConfigManager(args.config)
        config = config_manager.config
    except Exception as e:
        print(f"❌ Error loading configuration: {e}", file=sys.stderr)
        return 1

    print("\n📂 Task Source Directories:")

    if not config.task_source_directories:
        print("  (none)")
        return 0

    for source_dir in config.task_source_directories:
        print(f"\n  📁 {source_dir.id}")
        print(f"      Path: {source_dir.path}")
        print(f"      Description: {source_dir.description or '(no description)'}")
        print(f"      Added: {source_dir.added_at}")

    return 0


def cmd_unregister(args):
    """Remove (unregister) a Task Source Directory."""
    try:
        config_manager = ConfigManager(args.config)
        config = config_manager.config

        # Check if source exists
        source_dir = config.get_task_source_directory(args.source_id)
        if not source_dir:
            print(f"❌ Task Source Directory '{args.source_id}' not found")
            return 1

        # Remove it
        if config.remove_task_source_directory(args.source_id):
            config_manager.save_config()
            print(f"✅ Unregistered Task Source Directory '{args.source_id}'")

            # Restart daemon to apply changes
            _restart_daemon()
            return 0
        else:
            print(f"❌ Failed to remove Task Source Directory '{args.source_id}'")
            return 1

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


def cmd_run(args):
    """Run task queue interactively (for testing)."""
    import time

    try:
        config_manager = ConfigManager(args.config)
        config = config_manager.config

        if not config.project_workspace:
            print("❌ No Project Workspace set")
            return 1

        task_runner = TaskRunner(
            project_workspace=config.project_workspace
        )

        source_dirs = config.task_source_directories

        print("=" * 60)
        print("🔄 Running Task Queue (Interactive Mode)")
        print("=" * 60)
        print(f"Configuration: {args.config}")
        print(f"Task Source Directories: {len(source_dirs)}")
        print()

        cycles = args.cycles if args.cycles > 0 else 999999

        for cycle in range(cycles):
            print(f"\n--- Cycle {cycle + 1} ---")

            # Pick next task
            task_file = task_runner.pick_next_task(source_dirs)

            if task_file:
                print(f"Found task: {task_file.name}")
                result = task_runner.execute_task(task_file)
                print(f"Status: {result['status']}")
                if result.get("error"):
                    print(f"Error: {result['error']}")
            else:
                print("No pending tasks")

            # Check if any tasks exist
            status = task_runner.get_status(source_dirs)
            if status['pending'] == 0:
                print("\n✅ All tasks processed")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1

    return 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Task Queue CLI (Directory-Based State)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize task system from current directory
  task-queue init

  # Check status
  task-queue status

  # Register a Task Source Directory (advanced)
  task-queue register \\
    --task-source-dir tasks/task-documents \\
    --project-workspace /path/to/project \\
    --source-id main

  # Run interactively
  task-queue run --cycles 5

  # List source directories
  task-queue list-sources

  # Unregister a source directory
  task-queue unregister --source-id main
        """
    )

    # Global arguments
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to configuration file"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize task system from current directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize from current directory
  task-queue init

  # Re-initialize (replace existing configuration)
  task-queue init --force

  # Initialize but skip existing queues
  task-queue init --skip-existing

  # Initialize and restart daemon
  task-queue init --restart-daemon

This command creates the directory structure for ad-hoc and planned task queues,
then registers them as Task Source Directories. The current directory is used as
the Project Workspace.
        """
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-initialize even if already set up (replaces existing queues)"
    )
    init_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip queues that are already registered"
    )
    init_parser.add_argument(
        "--restart-daemon",
        action="store_true",
        help="Restart the task-queue daemon after initialization"
    )
    init_parser.set_defaults(func=cmd_init)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.set_defaults(func=cmd_status)

    # Register command
    register_parser = subparsers.add_parser("register", help="Register Task Source Directory")
    register_parser.add_argument(
        "--task-source-dir",
        required=True,
        help="Path to Task Source Directory"
    )
    register_parser.add_argument(
        "--project-workspace",
        required=True,
        help="Path to Project Workspace"
    )
    register_parser.add_argument(
        "--source-id",
        required=True,
        help="Unique ID for this source"
    )
    register_parser.set_defaults(func=cmd_register)

    # List sources command
    list_sources_parser = subparsers.add_parser("list-sources", help="List Task Source Directories")
    list_sources_parser.set_defaults(func=cmd_list_sources)

    # Unregister command
    unregister_parser = subparsers.add_parser("unregister", help="Remove Task Source Directory")
    unregister_parser.add_argument(
        "--source-id",
        required=True,
        help="Task Source Directory ID to remove"
    )
    unregister_parser.set_defaults(func=cmd_unregister)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run task queue interactively")
    run_parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of cycles (0 = infinite)"
    )
    run_parser.set_defaults(func=cmd_run)

    # Parse arguments
    args = parser.parse_args()

    # Set default config file if not specified
    if not args.config:
        args.config = DEFAULT_CONFIG_FILE

    # Execute command
    if hasattr(args, 'func'):
        return args.func(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
