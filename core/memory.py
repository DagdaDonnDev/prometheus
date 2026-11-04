"""
Persistent memory system.
Tracks who the user is, what they have, what they've done.
Shared across all tabs.
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


MEMORY_PATH = "memory/user_memory.json"


class Memory:
    def __init__(self):
        self.data = self._default()
        self.load()

    def _default(self) -> Dict[str, Any]:
        return {
            "user": {
                "name": None,
                "day_count": 1,
                "start_date": None,
                "location_estimate": None,
                "known_skills": [],
                "mentioned_people": [],
                "psychological_state": "unknown",
                "notes": []
            },
            "inventory": {
                "tools": [],
                "materials": [],
                "food_days": None,
                "water_days": None,
                "shelter_status": None,
                "power_source": None,
                "medical_supplies": []
            },
            "progress": {
                "completed": [],
                "in_progress": [],
                "planned": []
            },
            "alerts": {
                "medical_condition": None,
                "immediate_danger": None,
                "critical_shortage": None
            },
            "significant_moments": [],
            "last_updated": datetime.now().isoformat()
        }

    def load(self):
        if os.path.exists(MEMORY_PATH):
            try:
                with open(MEMORY_PATH, "r") as f:
                    saved = json.load(f)
                # Merge with defaults (handles new fields)
                self._deep_merge(self.data, saved)
            except Exception:
                pass  # Use defaults if corrupt

    def save(self):
        os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
        self.data["last_updated"] = datetime.now().isoformat()
        with open(MEMORY_PATH, "w") as f:
            json.dump(self.data, f, indent=2)

    def reset(self):
        """Reset memory to defaults and save."""
        self.data = self._default()
        self.save()

    def _deep_merge(self, base: dict, update: dict):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get_context_string(self) -> str:
        """Returns a compact summary of user state for injection into prompts."""
        u = self.data["user"]
        inv = self.data["inventory"]
        alerts = self.data["alerts"]

        parts = []

        if u["name"]:
            parts.append(f"User's name: {u['name']}")

        parts.append(f"Day: {u['day_count']}")

        if u["location_estimate"]:
            parts.append(f"Estimated location: {u['location_estimate']}")

        if u["known_skills"]:
            parts.append(f"Known skills: {', '.join(u['known_skills'])}")

        if u["mentioned_people"]:
            parts.append(f"People mentioned: {', '.join(u['mentioned_people'])}")

        if inv["shelter_status"]:
            parts.append(f"Shelter: {inv['shelter_status']}")

        if inv["food_days"] is not None:
            parts.append(f"Food supply: ~{inv['food_days']} days")

        if inv["water_days"] is not None:
            parts.append(f"Water supply: ~{inv['water_days']} days")

        if alerts["medical_condition"]:
            parts.append(f"⚠️ Medical: {alerts['medical_condition']}")

        if alerts["immediate_danger"]:
            parts.append(f"🚨 Danger: {alerts['immediate_danger']}")

        if alerts["critical_shortage"]:
            parts.append(f"⚠️ Shortage: {alerts['critical_shortage']}")

        if self.data["significant_moments"]:
            recent = self.data["significant_moments"][-3:]
            parts.append(f"Recent events: {'; '.join(recent)}")

        return "\n".join(parts) if parts else "No user context yet."

    def add_moment(self, moment: str):
        day = self.data["user"]["day_count"]
        self.data["significant_moments"].append(f"Day {day}: {moment}")
        # Keep last 50
        self.data["significant_moments"] = self.data["significant_moments"][-50:]
        self.save()

    def increment_day(self):
        self.data["user"]["day_count"] += 1
        self.save()

    def set_name(self, name: str):
        self.data["user"]["name"] = name
        self.save()

    def update_inventory(self, key: str, value):
        if key in self.data["inventory"]:
            self.data["inventory"][key] = value
            self.save()

    def set_alert(self, alert_type: str, value: Optional[str]):
        if alert_type in self.data["alerts"]:
            self.data["alerts"][alert_type] = value
            self.save()
