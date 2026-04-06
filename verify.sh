#!/usr/bin/env bash
set -euo pipefail

echo "=== XRPL Lab — verify ==="

echo "--- lint ---"
ruff check xrpl_lab/ tests/

echo "--- test ---"
pytest tests/ -v --tb=short

echo "--- build ---"
pip install build -q
python -m build --sdist --wheel

echo "=== All checks passed ==="
