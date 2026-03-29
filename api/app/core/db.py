import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _database_path() -> str:
    return os.getenv("DATABASE_PATH", "/data/nestra_demo.db")


@contextmanager
def get_db() -> sqlite3.Connection:
    db_path = _database_path()
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
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS tenants (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS households (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              name TEXT NOT NULL,
              timezone TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS actors (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              household_id TEXT NOT NULL,
              name TEXT NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('owner', 'resident', 'guest')),
              created_at TEXT NOT NULL,
              FOREIGN KEY (tenant_id) REFERENCES tenants(id),
              FOREIGN KEY (household_id) REFERENCES households(id)
            );

            CREATE TABLE IF NOT EXISTS devices (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              household_id TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              room TEXT,
              online INTEGER NOT NULL,
              last_seen TEXT NOT NULL,
              state_json TEXT NOT NULL,
              FOREIGN KEY (tenant_id) REFERENCES tenants(id),
              FOREIGN KEY (household_id) REFERENCES households(id)
            );

            CREATE TABLE IF NOT EXISTS device_intents (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              household_id TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              intent_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL,
              requires_confirmation INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              confirmed_at TEXT,
              FOREIGN KEY (tenant_id) REFERENCES tenants(id),
              FOREIGN KEY (household_id) REFERENCES households(id),
              FOREIGN KEY (actor_id) REFERENCES actors(id)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
              event_id TEXT PRIMARY KEY,
              occurred_at TEXT NOT NULL,
              tenant_id TEXT NOT NULL,
              household_id TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              actor_role TEXT NOT NULL,
              action TEXT NOT NULL,
              resource_type TEXT NOT NULL,
              resource_id TEXT NOT NULL,
              outcome TEXT NOT NULL,
              reason TEXT,
              metadata_json TEXT NOT NULL,
              FOREIGN KEY (tenant_id) REFERENCES tenants(id),
              FOREIGN KEY (household_id) REFERENCES households(id),
              FOREIGN KEY (actor_id) REFERENCES actors(id)
            );
            """
        )

        now = _utc_now()
        conn.execute(
            """
            INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name
            """,
            ("default-tenant", "Nestra Demo Tenant", now),
        )
        conn.execute(
            """
            INSERT INTO households (id, tenant_id, name, timezone, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              tenant_id = excluded.tenant_id,
              name = excluded.name,
              timezone = excluded.timezone
            """,
            ("default-home", "default-tenant", "Amonkar Household", "Europe/Amsterdam", now),
        )

        actors = [
            ("owner-1", "default-tenant", "default-home", "Sidhant", "owner", now),
            ("resident-1", "default-tenant", "default-home", "Mia", "resident", now),
            ("guest-1", "default-tenant", "default-home", "Guest", "guest", now),
        ]
        conn.executemany(
            """
            INSERT INTO actors (id, tenant_id, household_id, name, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              tenant_id = excluded.tenant_id,
              household_id = excluded.household_id,
              name = excluded.name,
              role = excluded.role
            """,
            actors,
        )

        devices = [
            (
                "dev-001",
                "default-tenant",
                "default-home",
                "Living Room Thermostat",
                "thermostat",
                "living-room",
                1,
                now,
                json.dumps({"target_temperature_c": 22.0}),
            ),
            (
                "dev-002",
                "default-tenant",
                "default-home",
                "Main Door Lock",
                "lock",
                "entryway",
                1,
                now,
                json.dumps({"lock_state": "locked"}),
            ),
            (
                "dev-003",
                "default-tenant",
                "default-home",
                "EV Charger",
                "plug",
                "garage",
                1,
                now,
                json.dumps({"on_off": False}),
            ),
            (
                "dev-004",
                "default-tenant",
                "default-home",
                "Kitchen Lights",
                "light",
                "kitchen",
                1,
                now,
                json.dumps({"on_off": True, "brightness": 72}),
            ),
            (
                "dev-005",
                "default-tenant",
                "default-home",
                "Front Door Camera",
                "camera",
                "entryway",
                1,
                now,
                json.dumps({}),
            ),
            (
                "dev-006",
                "default-tenant",
                "default-home",
                "Bedroom Air Quality Sensor",
                "sensor",
                "bedroom",
                1,
                now,
                json.dumps({}),
            ),
            (
                "dev-007",
                "default-tenant",
                "default-home",
                "Living Room Blinds",
                "blind",
                "living-room",
                1,
                now,
                json.dumps({}),
            ),
        ]
        conn.executemany(
            """
            INSERT INTO devices (
              id, tenant_id, household_id, name, type, room, online, last_seen, state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              type = excluded.type,
              room = excluded.room,
              online = excluded.online,
              state_json = excluded.state_json
            """,
            devices,
        )

        conn.execute(
            """
            INSERT INTO audit_events (
              event_id, occurred_at, tenant_id, household_id, actor_id, actor_role,
              action, resource_type, resource_id, outcome, reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                "evt_seed_001",
                now,
                "default-tenant",
                "default-home",
                "owner-1",
                "owner",
                "integration.sync",
                "integration",
                "matter-homeassistant",
                "allowed",
                None,
                json.dumps({"providers": ["Matter", "Home Assistant"], "status": "connected"}),
            ),
        )
