#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Running tests with coverage..."

run_coverage() {
    python3 -m pytest tests/ --cov=daily_brief --cov-report=term-missing --cov-report=xml "$@"
    return $?
}

EXIT_CODE=0
run_coverage || EXIT_CODE=$?
set +e

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Coverage report generated (term-missing + coverage.xml)."
else
    echo "❌ Tests failed during coverage run (exit code: $EXIT_CODE)."
fi
exit $EXIT_CODE
