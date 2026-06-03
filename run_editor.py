#!/usr/bin/env python3
"""Launch the semantic document editor."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from editor.main import main

if __name__ == "__main__":
    main()
