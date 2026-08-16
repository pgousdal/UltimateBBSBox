#!/usr/bin/env python3
"""Canonical hyphenated dashboard entrypoint; delegates to ubb_dashboard.py."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('ubb_dashboard.py')), run_name='__main__')
