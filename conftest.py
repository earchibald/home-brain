"""
Root conftest.py - Set up Python path before test collection.

This file is loaded by pytest before any test modules are imported,
allowing us to add the implementation directory to sys.path.
"""

import sys
from pathlib import Path

# Add the implementation directory to Python path so imports work correctly
impl_root = Path(__file__).parent
sys.path.insert(0, str(impl_root))
