#!/usr/bin/env python3
"""Entry point for the CDC consumer."""

import sys
import os

# Add src/ to path so `consumer` package is importable
sys.path.insert(0, os.path.dirname(__file__))

from consumer.runner import main

if __name__ == "__main__":
    main()
