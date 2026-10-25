"""Thin wrapper for backend/scripts/seed_data.py.

Allows running `python scripts/seed_data.py` from the project root.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "scripts.seed_data":
    backend_script = backend_dir / "scripts" / "seed_data.py"
    spec = importlib.util.spec_from_file_location("scripts.seed_data", backend_script)
    if spec and spec.loader:
        backend_mod = importlib.util.module_from_spec(spec)
        sys.modules["scripts.seed_data"] = backend_mod
        spec.loader.exec_module(backend_mod)
        seed = backend_mod.seed
else:
    from scripts.seed_data import seed

if __name__ == "__main__":
    asyncio.run(seed())
