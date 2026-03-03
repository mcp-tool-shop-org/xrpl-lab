"""Allow running as `python -m xrpl_lab` (used by PyInstaller)."""
import sys

# PyInstaller on Windows may inherit cp1252 encoding which can't handle
# Unicode characters used by Rich (○, ✓, ✗, etc.). Reconfigure to UTF-8.
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from xrpl_lab.cli import main

if __name__ == "__main__":
    main()
