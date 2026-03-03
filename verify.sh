#!/usr/bin/env bash
set -euo pipefail

echo "=== XRPL Lab — verify ==="

echo "--- lint ---"
ruff check xrpl_lab/ tests/

echo "--- test ---"
pytest tests/ -v --tb=short

echo "--- build ---"
python -m build --sdist --wheel

echo "=== All checks passed ==="
