#!/bin/bash
# Test script for task-monitor

set -e

echo "==================================="
echo "Running Task Monitor Test Suite"
echo "==================================="
echo ""

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run tests
echo "Running model and config tests..."
python3 -m pytest tests/test_models.py tests/test_config.py tests/test_file_utils.py -v

echo ""
echo "==================================="
echo "Variable Naming Convention (Updated)"
echo "==================================="
echo ""
echo "✅ queue         - Queue object (e.g., Queue(id='ad-hoc', path='...'))"
echo "✅ queue_path    - Path to queue directory (e.g., Path('/tasks/ad-hoc'))"
echo "✅ pending_dir   - Path to pending/ (e.g., queue_path / 'pending')"
echo "✅ task_file     - Path to task .md file"
echo "✅ task_id       - Task ID from filename (e.g., 'task-20250131-120000')"
echo ""
echo "Note: 'task_spec_dir' has been replaced with 'pending_dir'"
echo "      'task_doc_dir' was the old v1.0 term (now 'queue')"
