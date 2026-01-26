from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_SRC = ROOT / "packages" / "db" / "src"
ENGINE_SRC = ROOT / "packages" / "engine"

for path in (DB_SRC, ENGINE_SRC):
    if path.exists():
        sys.path.insert(0, str(path))
