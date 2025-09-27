#!/usr/bin/env bash
set -euo pipefail

echo "🧹 Cleaning project files..."

# Python cache files
echo "  - Removing Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Virtual environment
if [[ -d ".venv" ]]; then
    echo "  - Removing virtual environment..."
    rm -rf .venv
fi

# UV cache
if [[ -d ".uv" ]]; then
    echo "  - Removing UV cache..."
    rm -rf .uv
fi

# Test files and temp directories
echo "  - Removing test files..."
rm -rf test_emails/ test_worker_emails/ test_worker/ json_test/ 2>/dev/null || true
rm -f test_*.py 2>/dev/null || true

# Log files
echo "  - Removing log files..."
find . -name "*.log" -delete 2>/dev/null || true

# OS-specific files
echo "  - Removing OS files..."
find . -name ".DS_Store" -delete 2>/dev/null || true
find . -name "Thumbs.db" -delete 2>/dev/null || true
find . -name "._*" -delete 2>/dev/null || true

# IDE files
echo "  - Removing IDE files..."
rm -rf .vscode/ .idea/ 2>/dev/null || true

# Coverage files
echo "  - Removing coverage files..."
rm -f .coverage 2>/dev/null || true
rm -rf htmlcov/ 2>/dev/null || true

# Build artifacts
echo "  - Removing build artifacts..."
rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

echo "✅ Project cleaned successfully!"
