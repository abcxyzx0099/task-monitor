# Task Monitor

A task monitoring and execution system that processes task specifications using the Claude Agent SDK. Features event-driven file monitoring with parallel worker architecture and file-based running task status tracking.

## Architecture Overview

```
[Task Monitor System - v2.1 Directory-Based State with Parallel Workers & Status Tracking]

Queue A                          Queue B
tasks/ad-hoc/                    tasks/planned/
[pending/task-a1.md]             [pending/task-b1.md]
[pending/task-a2.md]             [pending/task-b2.md]
     │                                  │
     │ [.ad-hoc.running]              │ [.planned.running]
     │ contains "task-a1"              │ contains "task-b1"
     │                                  │
     ▼                                  ▼
┌─────────────────┐            ┌─────────────────┐
│  Worker Thread  │            │  Worker Thread  │
│  for Queue A    │            │  for Queue B    │
│                 │            │                 │
│  Sequential     │            │  Sequential     │
│  FIFO Queue     │            │  FIFO Queue     │
│                 │            │                 │
│ task-a1 → a2    │            │ task-b1 → b2    │
└─────────────────┘            └─────────────────┘
     │                                  │
     └────────────────┬─────────────────┘
                      │
                      ▼
              ┌──────────────────────────────────────────────┐
              │         Project Workspace (single)          │
              │    /home/admin/workspaces/datachat          │
              └──────────────────────────────────────────────┘

Execution Model:
- Within each queue: Sequential (one task at a time)
- Across queues: Parallel (multiple workers run simultaneously)
```

## Key Concepts

| Concept | Term | Definition |
|---------|------|------------|
| **1** | **Queue** | A folder containing task document files in `pending/`. Watched for file changes. |
| **2** | **Task Document** | Individual task specification file (e.g., `task-YYYYMMDD-HHMMSS-description.md`). |
| **3** | **Project Workspace** | The working directory where Claude Agent SDK executes. |
| **4** | **Directory-Based State** | File system is the source of truth. `.running` files provide status visibility. |

## Features

### Core Features

| Feature | Description |
|---------|-------------|
| **Event-Driven** | Watchdog detects file changes instantly (no polling delay) |
| **Parallel Workers** | One worker thread per Queue |
| **Sequential Within Queue** | Tasks from same queue execute one at a time (FIFO) |
| **Parallel Across Queues** | Different queues execute simultaneously |
| **Directory-Based State** | No state file - filesystem structure is the source of truth |
| **Status File Tracking** | `.{queue_id}.running` files provide CLI visibility of running tasks |
| **JSON Result Files** | Captures execution metadata, cost, token usage per task |
| **Auto-Load on Create** | Watchdog auto-detects new Task Documents |
| **Claude Agent SDK Integration** | Executes tasks via `/task-execution` skill |
| **Daemon Service** | Runs as systemd user service for continuous processing |

### Execution Model

**Same queue:** Sequential FIFO (task-a1 → task-a2 → task-a3)

**Different queues:** Parallel (A-1 and B-1 run simultaneously)

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│              ONE DAEMON PROCESS (PID-locked)            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Thread 1     │  │ Thread 2     │  │ Thread 3     │ │
│  │ ↓            │  │ ↓            │  │ ↓            │ │
│  │ Queue A      │  │ Queue B      │  │ Queue C      │ │
│  │ (Sequential) │  │ (Sequential) │  │ (Sequential) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│           1 Thread per Queue (1:1 mapping)              │
└─────────────────────────────────────────────────────────┘
```

| Component | Count | Behavior |
|-----------|-------|----------|
| Process | 1 | Single daemon (PID lock prevents multiples) |
| Threads | N | One worker thread per Queue |
| Per Queue | Sequential | Tasks execute one at a time (FIFO) |
| Across Queues | Parallel | Multiple queues run simultaneously |

### Running Status File

When a task is running, a `.running` file is created in the queue directory:

**Location:** `tasks/{queue}/.{queue_id}.running`

**Format:** Plain text file containing the task ID

```
task-20260207-123456-fix-bug
```

**Purpose:**
- Provide CLI visibility of currently running task
- Enable status queries without IPC complexity
- Simple file-based inter-process communication

**Note:** The `.running` file is for **visibility only**, not locking. The daemon's single-threaded worker per queue prevents concurrent execution.

## Directory Structure

```
{project_workspace}/           # e.g., /home/admin/workspaces/datachat
└── tasks/                     # Parent of all queues
    ├── ad-hoc/                # Queue
    │   ├── .ad-hoc.running    # Status file (exists when task running)
    │   ├── pending/           # Task input (watchdog monitors)
    │   │   └── task-*.md
    │   ├── completed/         # Completed tasks
    │   ├── failed/            # Failed tasks
    │   ├── results/           # Result JSON files
    │   └── reports/           # Worker execution reports
    │
    └── planned/               # Queue
        ├── .planned.running    # Status file (exists when task running)
        ├── pending/           # Task input (watchdog monitors)
        │   └── task-*.md
        ├── completed/
        ├── failed/
        ├── planning/          # Planning documents
        ├── results/           # Result JSON files
        └── reports/
```

## Installation

```bash
cd /home/admin/workspaces/task-monitor
pip install -e .
```

## CLI Usage

```bash
# System commands
task-monitor init                           # Initialize task system
task-monitor status                         # Show system status
task-monitor status --detailed              # Show detailed status

# Queue commands
task-monitor queues list                    # List configured queues
task-monitor queues add <path> --id <id>    # Add a queue
task-monitor queues rm --queue-id <id>      # Remove a queue

# Task commands
task-monitor tasks show <task-id>           # Show task document path
task-monitor tasks logs <task-id>           # Show result JSON
task-monitor tasks cancel <task-id>         # Cancel a running task

# Worker commands
task-monitor workers status                 # Show detailed worker status
task-monitor workers list                   # List workers

# Logs
task-monitor logs                           # Show daemon logs
task-monitor logs --follow                  # Follow logs live
```

## Configuration

Configuration is stored in `~/.config/task-monitor/config.json`:

```json
{
  "version": "2.0",
  "settings": {
    "watch_enabled": true,
    "watch_debounce_ms": 500,
    "watch_patterns": ["task-*.md"],
    "max_attempts": 3
  },
  "project_workspace": "/path/to/project",
  "queues": [
    {
      "id": "ad-hoc",
      "path": "/path/to/tasks/ad-hoc",
      "description": "Ad-hoc task queue",
      "added_at": "2026-02-07T12:00:00"
    }
  ]
}
```

## Daemon Service

The monitor runs as a systemd user service:

```bash
# Start daemon
systemctl --user start task-monitor.service

# Stop daemon
systemctl --user stop task-monitor.service

# Restart daemon
systemctl --user restart task-monitor.service

# Enable at login
systemctl --user enable task-monitor.service

# View logs
journalctl --user -u task-monitor.service -f
```

## Per-Queue Architecture

The monitor uses **per-queue worker threads** with these rules:

| Rule | Description |
|------|-------------|
| **Same queue** | Sequential FIFO execution (one at a time) |
| **Different queues** | Parallel execution (can run simultaneously) |
| **Worker threads** | One thread per Queue |
| **Status tracking** | `.{queue_id}.running` file provides running task ID |

## Key Principles

1. **Event-Driven Monitoring** - Watchdog detects file changes instantly
2. **Per-Queue Worker Threads** - One worker thread per Queue
3. **Sequential Within Queue** - Prevents file conflict race conditions
4. **Parallel Across Queues** - Different queues can execute simultaneously
5. **Background Processing** - Daemon runs independently with watchdog
6. **File-Based Status Tracking** - `.running` files provide CLI visibility
7. **No Locking Required** - Single-threaded worker per queue ensures serialization

## Version History

- **v2.1** - Replaced lock file tracking with simple `.running` status files for CLI visibility
- **v2.0** - Simplified directory-based state, no state file
