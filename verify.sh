#!/usr/bin/env bash
set -euo pipefail

echo "=== XRPL Lab — verify ==="

echo "--- lint ---"
ruff check xrpl_lab/ tests/

echo "--- test ---"
pytest tests/ -v --tb=short

echo "--- security: pip-audit ---"
if command -v pip-audit >/dev/null 2>&1; then
    pip-audit --strict || { echo "pip-audit found vulnerabilities"; exit 1; }
else
    echo "pip-audit not installed; skipping (install via uv add --dev pip-audit)"
fi

echo "--- security: lock file integrity ---"
if [ -f uv.lock ]; then
    uv lock --check || { echo "uv.lock out of date with pyproject.toml"; exit 1; }
fi

echo "--- build ---"
uv build

echo "=== All checks passed ==="
