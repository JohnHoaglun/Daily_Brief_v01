#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Running tests with coverage..."
python3 -m pytest tests/ --cov=daily_brief --cov-report=term-missing --cov-report=html:coverage_html "$@"
