"""
Memory Relevance Filter
=======================
Scores memory entries by relevance to the current query.
Injects only the most relevant context to avoid prompt dilution.

Prevents:
  - Injecting irrelevant inventory into medical queries
  - Injecting psychological state into electronics queries
  - Diluting RAG effectiveness with noise
"""

from typing import Dict, List, Tuple, Any


# Memory fields and their topic relevance
FIELD_TOPICS = {
    # Always relevant
    "name":               ["all"],
    "day_count":          ["all"],
    "location_estimate":  ["survival", "navigation", "farming", "medical"],

    # Conditionally relevant
    "known_skills":       ["build", "electronics", "farming", "chemistry", "medical"],
    "mentioned_people":   ["prometheus"],
    "psychological_state":["prometheus", "medical"],

    # Inventory fields
    "tools":              ["build", "electronics", "farming"],
    "materials":          ["build", "chemistry", "electronics"],
    "food_days":          ["survival", "farming", "prometheus"],
    "water_days":         ["survival", "navigation"],
    "shelter_status":     ["survival", "build"],
    "power_source":       ["electronics", "survival"],
    "medical_supplies":   ["medical"],

    # Alerts — always relevant if set
    "medical_condition":  ["medical", "prometheus", "survival"],
    "immediate_danger":   ["survival", "navigation", "all"],
    "critical_shortage":  ["survival", "farming", "prometheus"],

    # Progress — relevant to planning
    "completed":          ["prometheus", "build", "farming"],
    "in_progress":        ["build", "farming", "prometheus"],
}

# Keywords that boost relevance of specific memory fields
KEYWORD_BOOSTS = {
    "food_days":       ["food", "eat", "hungry", "starv", "nutrition"],
    "water_days":      ["water", "thirst", "dehydr", "drink"],
    "medical_supplies":["medic", "treat", "wound", "sick", "injur"],
    "shelter_status":  ["shelter", "cold", "warm", "house", "camp"],
    "tools":           ["build", "make", "construct", "tool", "fix"],
    "materials":       ["material", "build", "make", "construct"],
    "power_source":    ["power", "electric", "solar", "battery", "charge"],
    "known_skills":    ["skill", "know", "expert", "can you", "able to"],
    "psychological_state": ["feel", "emotion", "stress", "cope", "mental"],
    "location_estimate":   ["where", "location", "here", "area", "region"],
}


class MemoryRelevanceFilter:
    """
    Filters and ranks memory entries by relevance to a query + tab.
    Returns a compact, relevant context string.
    """

    def filter(
        self,
        memory_data: Dict,
        query: str,
        tab_id: str,
        max_fields: int = 8,
    ) -> str:
        """
        Score all memory fields for relevance.
        Return formatted string of top-N most relevant fields.
        """
        q = query.lower()
        scored_fields: List[Tuple[float, str, str]] = []  # (score, label, value)

        user = memory_data.get("user", {})
        inv  = memory_data.get("inventory", {})
        alerts = memory_data.get("alerts", {})
        progress = memory_data.get("progress", {})

        # ── Score each field ───────────────────────────────────────────────

        def score_field(field_name: str, value: Any, label: str) -> float:
            if not value:
                return 0.0

            topics = FIELD_TOPICS.get(field_name, [])
            base_score = 0.0

            # Always relevant fields
            if "all" in topics:
                base_score = 1.0
            # Tab-relevant fields
            elif tab_id in topics:
                base_score = 0.8
            # Adjacent topics
            else:
                base_score = 0.1

            # Keyword boost
            keywords = KEYWORD_BOOSTS.get(field_name, [])
            boost = sum(0.3 for kw in keywords if kw in q)
            base_score = min(1.0, base_score + boost)

            return base_score

        # User fields
        name = user.get("name")
        if name:
            scored_fields.append((1.0, "Name", name))

        day = user.get("day_count", 1)
        scored_fields.append((1.0, "Day", str(day)))

        loc = user.get("location_estimate")
        if loc:
            s = score_field("location_estimate", loc, "Location")
            scored_fields.append((s, "Location", loc))

        skills = user.get("known_skills", [])
        if skills:
            s = score_field("known_skills", skills, "Skills")
            scored_fields.append((s, "Skills", ", ".join(skills[:5])))

        people = user.get("mentioned_people", [])
        if people:
            s = score_field("mentioned_people", people, "People")
            scored_fields.append((s, "People mentioned", ", ".join(people[:3])))

        psych = user.get("psychological_state")
        if psych and psych != "unknown":
            s = score_field("psychological_state", psych, "State")
            scored_fields.append((s, "Psychological state", psych))

        # Inventory fields
        for field, label in [
            ("food_days",       "Food supply"),
            ("water_days",      "Water supply"),
            ("shelter_status",  "Shelter"),
            ("power_source",    "Power"),
        ]:
            val = inv.get(field)
            if val is not None:
                s = score_field(field, val, label)
                display = f"~{val} days" if "days" in field else str(val)
                scored_fields.append((s, label, display))

        tools = inv.get("tools", [])
        if tools:
            s = score_field("tools", tools, "Tools")
            scored_fields.append((s, "Tools", ", ".join(tools[:5])))

        materials = inv.get("materials", [])
        if materials:
            s = score_field("materials", materials, "Materials")
            scored_fields.append((s, "Materials", ", ".join(materials[:5])))

        med_sup = inv.get("medical_supplies", [])
        if med_sup:
            s = score_field("medical_supplies", med_sup, "Medical supplies")
            scored_fields.append((s, "Medical supplies", ", ".join(med_sup[:5])))

        # Alerts — always high priority if set
        for alert_field, label in [
            ("medical_condition", "⚠ Medical"),
            ("immediate_danger",  "🚨 Danger"),
            ("critical_shortage", "⚠ Shortage"),
        ]:
            val = alerts.get(alert_field)
            if val:
                scored_fields.append((0.95, label, val))

        # Progress — relevant for planning
        completed = progress.get("completed", [])
        if completed:
            s = score_field("completed", completed, "Completed")
            scored_fields.append((s, "Completed", ", ".join(completed[-3:])))

        in_prog = progress.get("in_progress", [])
        if in_prog:
            s = score_field("in_progress", in_prog, "In progress")
            scored_fields.append((s, "In progress", ", ".join(in_prog[:3])))

        # ── Sort and take top N ────────────────────────────────────────────
        scored_fields.sort(key=lambda x: x[0], reverse=True)
        top_fields = [(label, value) for _, label, value
                      in scored_fields[:max_fields] if _  > 0.1]

        if not top_fields:
            return ""

        lines = [f"{label}: {value}" for label, value in top_fields]
        return "\n".join(lines)
