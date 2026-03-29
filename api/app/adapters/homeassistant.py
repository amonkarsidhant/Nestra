"""
Home Assistant adapter.

This adapter synchronizes devices with a Home Assistant instance and executes
service calls for device actions.

Environment variables:
- HA_URL: Home Assistant base URL (e.g., https://ha.example.com)
- HA_TOKEN: Long‑lived access token
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class HaEntity:
    entity_id: str
    state: str
    attributes: dict[str, Any]


class HomeAssistantError(Exception):
    """Raised when communication with Home Assistant fails."""


class HomeAssistantAdapter:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            allowed_methods=["GET", "POST"],
            status_forcelist=[502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )
        return session

    def ping(self) -> bool:
        try:
            r = self.session.get(f"{self.base_url}/api/", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_entities(self) -> list[HaEntity]:
        """Fetch all states from Home Assistant."""
        r = self.session.get(f"{self.base_url}/api/states", timeout=10)
        r.raise_for_status()
        data = r.json()
        entities = []
        for item in data:
            entity_id = item.get("entity_id", "")
            state = str(item.get("state", ""))
            attributes = item.get("attributes", {})
            entities.append(HaEntity(entity_id=entity_id, state=state, attributes=attributes))
        return entities

    def call_service(self, domain: str, service: str, service_data: dict[str, Any]) -> dict[str, Any]:
        """Invoke a Home Assistant service."""
        url = f"{self.base_url}/api/services/{domain}/{service}"
        r = self.session.post(url, json=service_data, timeout=10)
        r.raise_for_status()
        return r.json() if r.text else {}

    # Convenience mappings for common device types

    def turn_on(self, entity_id: str) -> None:
        self.call_service("homeassistant", "turn_on", {"entity_id": entity_id})

    def turn_off(self, entity_id: str) -> None:
        self.call_service("homeassistant", "turn_off", {"entity_id": entity_id})

    def toggle(self, entity_id: str) -> None:
        # HA toggle service may not exist; use toggle via light or switch depending on domain
        # Try generic toggle; if fails, caller should handle
        try:
            self.call_service("homeassistant", "toggle", {"entity_id": entity_id})
        except Exception:
            # Fallback: try light or switch toggle
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            if domain in ("light", "switch", "fan", "cover"):
                self.call_service(domain, "toggle", {"entity_id": entity_id})
            else:
                raise

    def set_light_brightness(self, entity_id: str, brightness_pct: int) -> None:
        # HA expects brightness_pct on light.turn_on
        self.call_service(
            "light",
            "turn_on",
            {"entity_id": entity_id, "brightness_pct": brightness_pct},
        )

    def lock(self, entity_id: str, state: str = "locked") -> None:
        # state: "locked" or "unlocked"
        self.call_service(
            "lock",
            "unlock" if state == "unlocked" else "lock",
            {"entity_id": entity_id},
        )

    def set_temperature(self, entity_id: str, temperature: float) -> None:
        # Climate set temperature; use temperature attribute
        self.call_service(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": temperature},
        )


def get_adapter_from_env() -> HomeAssistantAdapter | None:
    url = os.getenv("HA_URL", "").strip()
    token = os.getenv("HA_TOKEN", "").strip()
    if not url or not token:
        return None
    return HomeAssistantAdapter(base_url=url, token=token)
