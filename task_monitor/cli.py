import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime


# Default project root - can be overridden by --project-path argument
DEFAULT_PROJECT_ROOT = Path("/home/admin/workspaces/datachat")

# Task monitor path relative to project root (e.g., "tasks/task-monitor")
task_monitor_path = "tasks/task-monitor"


def show_task_status(task_id: str, project_root: Path = DEFAULT_PROJECT_ROOT):
    """Show status of a specific task across all stages (waiting, processing, completed)."""

    # Normalize task_id - ensure it has .md extension if just the base name
    if not task_id.endswith('.md'):
        task_id = f"{task_id}.md"

    state_file = project_root / task_monitor_path / "state" / "queue_state.json"
    items_dir = project_root / task_monitor_path / "pending"
    results_dir = project_root / task_monitor_path / "results"

    # 1. Check if currently processing
    if state_file.exists():
        with open(state_file, 'r') as f:
            state = json.load(f)

        current_task = state.get('current_task')
        if current_task and task_id in current_task:
            print(f"Status: processing")
            print(f"Task: {task_id}")
            print(f"Started: {state.get('task_start_time', 'Unknown')}")
            return

    # 2. Check if waiting in queue
    task_file = items_dir / task_id
    if task_file.exists():
        stat = task_file.stat()
        created_time = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"Status: waiting")
        print(f"Task: {task_id}")
        print(f"Created: {created_time}")
        print(f"Size: {stat.st_size} bytes")

        # Show position in queue if available
        if state_file.exists():
            with open(state_file, 'r') as f:
                state = json.load(f)
            queued_tasks = state.get('queued_tasks', [])
            if task_id in queued_tasks:
                position = queued_tasks.index(task_id) + 1
                print(f"Queue position: {position} of {len(queued_tasks)}")
        return

    # 3. Check if completed - try with .json extension for result file
    result_file = results_dir / task_id.replace('.md', '.json')
    if result_file.exists():
        with open(result_file) as f:
            data = json.load(f)

        # Show summary
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Task: {data.get('task_id', task_id)}")

        if 'duration_seconds' in data:
            print(f"Duration: {data['duration_seconds']:.2f} seconds")

        if 'worker_output' in data:
            worker_out = data['worker_output']
            if 'summary' in worker_out:
                print(f"\nSummary:")
                print(f"  {worker_out['summary']}")

            if 'usage' in worker_out:
                usage = worker_out['usage']
                print(f"\nUsage:")
                print(f"  Tokens: {usage.get('total_tokens', 'N/A')}")
                print(f"  Cost: ${usage.get('cost_usd', 0):.4f}")

        if 'error' in data:
            print(f"\nError: {data['error']}")
        return

    # 4. Not found anywhere
    print(f"Status: not_found")
    print(f"Task: {task_id}")
    print(f"\nThe task was not found in any of the following locations:")
    print(f"  - Currently processing")
    print(f"  - Waiting in queue ({items_dir})")
    print(f"  - Completed tasks ({results_dir})")


def check_daemon_running() -> bool:
    """Check if the monitor daemon process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "monitor_daemon"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        # Fallback: use ps and grep
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )
            return "monitor_daemon" in result.stdout and "grep -v grep" not in result.stdout
        except Exception:
            return False


def show_status(task_id: str = None, project_root: Path = DEFAULT_PROJECT_ROOT):
    """Show daemon status - simple check if service is running."""
    if task_id:
        show_task_status(task_id, project_root)
    else:
        daemon_running = check_daemon_running()
        print(f"{'Running' if daemon_running else 'Stopped'}")


def show_queue(project_root: Path = DEFAULT_PROJECT_ROOT):
    """Show current queue state."""
    state_file = project_root / task_monitor_path / "state" / "queue_state.json"
    if state_file.exists():
        with open(state_file, 'r') as f:
            state = json.load(f)
        print(f"Queue size: {state['queue_size']}")
        print(f"Processing: {state.get('current_task', 'None')}")
        if state.get('queued_tasks'):
            print("Queued tasks:")
            for i, task in enumerate(state['queued_tasks'], 1):
                print(f"  {i}. {task}")
    else:
        print("Queue state not available (monitor may not be running)")


def main():
    """CLI entry point - called by setuptools entry point."""
    parser = argparse.ArgumentParser(description="Task Monitor CLI")
    parser.add_argument("--project-path", "-p", type=str, help="Project root path")
    parser.add_argument("command", nargs="?", default="status", help="Command: status, queue, or task_id")
    args = parser.parse_args()

    # Project root - where tasks/{TASK_MONITOR_DIR}/pending, results, state directories are located
    project_root = Path(args.project_path) if args.project_path else DEFAULT_PROJECT_ROOT

    if args.command == "queue":
        show_queue(project_root)
    elif args.command == "status":
        show_status(None, project_root)
    else:
        show_status(args.command, project_root)


if __name__ == "__main__":
    main()
