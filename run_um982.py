#!/usr/bin/env python3
"""Run the UM982 CLI from a fresh clone without installing the package."""

import os
import sys

# src-layout keeps the package off sys.path; add it here so users need
# neither PYTHONPATH nor an editable install.
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)

from gnss_drivers.um982.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
