"""Pytest hooks — ensure web/dist is synced before route tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("SCANNER_WEB_DIR", str(ROOT / "web" / "dist"))
os.environ.setdefault("ELAB_INTEGRATION_LIVE", "false")
# Writable companion DB for local pytest (production data/ledger.db may be root-owned)
os.environ.setdefault("SCANNER_DB_PATH", str(ROOT / ".pytest_cache" / "test-ledger.db"))
os.environ.pop("OIDC_ISSUER", None)
os.environ.pop("OIDC_CLIENT_ID", None)
os.environ.pop("OIDC_CLIENT_SECRET", None)

Path(os.environ["SCANNER_DB_PATH"]).parent.mkdir(parents=True, exist_ok=True)

subprocess.run(["bash", str(ROOT / "scripts" / "sync_web_dist.sh")], check=True)
