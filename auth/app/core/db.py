import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.core.security import hash_password


def _db_path() -> str:
    return os.getenv("AUTH_DATABASE_PATH", "/data/nestra_auth.db")


@contextmanager
def get_db() -> sqlite3.Connection:
    db_path = _db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS demo_users (
              username TEXT PRIMARY KEY,
              password_hash TEXT NOT NULL,
              display_name TEXT NOT NULL,
              tenant_id TEXT NOT NULL,
              household_id TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              actor_role TEXT NOT NULL CHECK (actor_role IN ('owner', 'resident', 'guest')),
              created_at TEXT NOT NULL
            );
            """
        )

        seed_username = os.getenv("DEMO_OWNER_USERNAME", "owner@nestra.demo")
        existing = conn.execute(
            "SELECT username FROM demo_users WHERE username = ?", (seed_username,)
        ).fetchone()
        if existing:
            return

        seed_password = os.getenv("DEMO_OWNER_PASSWORD", "nestra-alpha-owner")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO demo_users (
              username, password_hash, display_name, tenant_id, household_id,
              actor_id, actor_role, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seed_username,
                hash_password(seed_password),
                "Sidhant",
                "default-tenant",
                "default-home",
                "owner-1",
                "owner",
                now,
            ),
        )
