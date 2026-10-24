#!/usr/bin/env python3
import sys
from pathlib import Path

# Ensure root package is in sys.path
root_dir = str(Path(__file__).parent.resolve())
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from bugslayer.cli import main

if __name__ == "__main__":
    main()
