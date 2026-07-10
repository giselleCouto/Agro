"""Isola os testes num banco SQLite temporário (antes de importar a app)."""
import os
import tempfile
from pathlib import Path

_db = Path(tempfile.gettempdir()) / "nokahi_test.db"
if _db.exists():
    _db.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db.as_posix()}"
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ["AGROROUTE_ADMIN_TOKEN"] = "test-admin-token"
