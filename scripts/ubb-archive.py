#!/usr/bin/env python3
"""CLI compatibility wrapper for the importable archive module."""
from ubb_archive import main

if __name__ == "__main__":
    raise SystemExit(main())
