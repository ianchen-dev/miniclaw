"""
Batch launcher for Claude Code tasks.
Splits tasks into batches to respect Claude's concurrency limit.
"""

import os
import sys
import time
from pathlib import Path


# Configuration
BATCH_NUM = 3  # Number of concurrent tasks per batch
INTERVAL_TIME = 60  # Seconds between batches (60000ms = 60s)

# Task directories
TASKS = [
    "cli",
    "concurrency",
    "delivery",
    "gateway",
    "intelligence",
    "prompts",
    "resilience",
    "scheduler",
    "tools",
]


def launch_batch(tasks: list[str], batch_num: int) -> None:
    """Launch a batch of tasks in separate cmd windows."""
    work_dir = Path.cwd()

    for task in tasks:
        # Build the command - match original bat file format exactly
        cmd = (
            f'start "{task}" cmd /k "cd /d {work_dir} && claude '
            f'"/code-simplifier @coder\\{task} ,done then commit" '
            f"--permission-mode acceptEdits --allowedTools "
            f'"Read,Write,Edit,Bash,Git,Npm,Pip""'
        )

        print(f"[Batch {batch_num}] Launching task: {task}")
        os.system(cmd)
        time.sleep(1)  # Small delay between each window


def main():
    print("Batch Launcher Configuration:")
    print(f"  - Batch size: {BATCH_NUM}")
    print(f"  - Interval: {INTERVAL_TIME}s")
    print(f"  - Total tasks: {len(TASKS)}")
    print(f"  - Total batches: {(len(TASKS) + BATCH_NUM - 1) // BATCH_NUM}")
    print("-" * 50)

    batch_count = 0

    # Split tasks into batches
    for i in range(0, len(TASKS), BATCH_NUM):
        batch_tasks = TASKS[i : i + BATCH_NUM]
        batch_count += 1

        print(f"\n=== Starting Batch {batch_count} ===")
        print(f"Tasks: {', '.join(batch_tasks)}")

        launch_batch(batch_tasks, batch_count)

        # Wait before next batch (unless this is the last batch)
        if i + BATCH_NUM < len(TASKS):
            print(f"\nWaiting {INTERVAL_TIME} seconds before next batch...")
            print("Previous batch windows will remain open.")
            time.sleep(INTERVAL_TIME)

    print("\n" + "=" * 50)
    print(f"All {len(TASKS)} tasks launched in {batch_count} batches!")
    print("Note: Windows remain open. Close manually when tasks complete.")


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            BATCH_NUM = int(sys.argv[1])
        except ValueError:
            print(f"Invalid batch number: {sys.argv[1]}, using default: {BATCH_NUM}")

    if len(sys.argv) > 2:
        try:
            INTERVAL_TIME = int(sys.argv[2])
        except ValueError:
            print(f"Invalid interval: {sys.argv[2]}, using default: {INTERVAL_TIME}")

    main()
