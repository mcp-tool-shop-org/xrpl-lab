"""Allow running as `python -m xrpl_lab` (used by PyInstaller)."""
from xrpl_lab.cli import main

if __name__ == "__main__":
    main()
