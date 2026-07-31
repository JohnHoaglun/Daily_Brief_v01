#!/bin/bash
set -euo pipefail

# Daily Brief — full test suite runner
cd "$(dirname "$0")/.."  # Navigate to project root

echo "╔══════════════════════════════════════════════════╗"
echo "║  Daily Brief Test Suite                         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Run all tests
python3 -m pytest tests/ -v --tb=short --color=yes "$@"

echo ""
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed."
else
    echo "❌ Tests failed (exit code: $EXIT_CODE)."
fi
exit $EXIT_CODE
