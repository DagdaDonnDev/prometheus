"""
Tab system - each tab is a focused conversation context
with its own history, summary, and knowledge domain.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime


TABS_PATH = "memory/tabs.json"


@dataclass
class Message:
    role: str        # "user" or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def _new_chat_id() -> str:
    import uuid
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def _title_from(text: str, limit: int = 48) -> str:
    """A chat's title: its first question, tidied and cut to length."""
    t = " ".join((text or "").split())
    return (t[:limit - 1].rstrip() + "…") if len(t) > limit else (t or "New chat")


@dataclass
class Tab:
    id: str
    name: str
    icon: str
    domains: List[str]
    system_prompt: str
    history: List[Dict] = field(default_factory=list)     # the CURRENT chat
    summary: str = ""
    custom: bool = False
    # Separate chats: the current one lives in history/summary above (so the
    # rest of the app is unchanged); earlier ones are kept here, untouched —
    # a new chat starts with no influence from them.
    chat_id: str = ""
    chat_title: str = ""
    chat_created: str = ""
    chats: List[Dict] = field(default_factory=list)

    def add_message(self, role: str, content: str):
        if not self.chat_id:
            self.chat_id = _new_chat_id()
            self.chat_created = datetime.now().isoformat()
        if role == "user" and not self.chat_title:
            self.chat_title = _title_from(content)
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    # ── Chats ──────────────────────────────────────────────────────────────

    def _current_as_record(self) -> Dict:
        updated = self.history[-1].get("timestamp", "") if self.history else self.chat_created
        return {
            "id": self.chat_id or _new_chat_id(),
            "title": self.chat_title or _title_from(next(
                (m["content"] for m in self.history if m["role"] == "user"), "New chat")),
            "created": self.chat_created or updated,
            "updated": updated,
            "history": self.history,
            "summary": self.summary,
        }

    def _archive_current(self):
        """Step 1 of switching: keep the current chat (if it has anything) in the list."""
        if not self.history and not self.summary:
            return
        record = self._current_as_record()
        self.chats = [c for c in self.chats if c["id"] != record["id"]] + [record]

    def _load_record(self, record: Dict):
        self.history = record.get("history", [])
        self.summary = record.get("summary", "")
        self.chat_id = record.get("id", "")
        self.chat_title = record.get("title", "")
        self.chat_created = record.get("created", "")

    def new_chat(self):
        """Keep this chat, start an empty one."""
        self._archive_current()
        self._load_record({})

    def open_chat(self, chat_id: str) -> bool:
        """Keep this chat, make an earlier one current."""
        if chat_id == self.chat_id:
            return True
        record = next((c for c in self.chats if c["id"] == chat_id), None)
        if record is None:
            return False
        self._archive_current()
        self.chats = [c for c in self.chats if c["id"] != chat_id]
        self._load_record(record)
        return True

    def delete_chat(self, chat_id: str):
        if chat_id == self.chat_id:
            self._load_record({})
        else:
            self.chats = [c for c in self.chats if c["id"] != chat_id]

    def rename_chat(self, chat_id: str, title: str):
        title = title.strip()[:80] or "Untitled chat"
        if chat_id == self.chat_id:
            self.chat_title = title
        for c in self.chats:
            if c["id"] == chat_id:
                c["title"] = title

    def all_chats(self, query: str = "") -> List[Dict]:
        """
        Every chat, newest first, the current one marked "current": True.
        With a query: only chats whose title or messages contain every word.
        """
        items = [dict(c, current=False) for c in self.chats]
        if self.history or self.summary:
            items.append(dict(self._current_as_record(), current=True))
        items.sort(key=lambda c: c.get("updated", ""), reverse=True)
        words = [w for w in query.lower().split() if w]
        if words:
            def text(c):
                return (c.get("title", "") + " " + c.get("summary", "") + " " +
                        " ".join(m.get("content", "") for m in c.get("history", []))).lower()
            items = [c for c in items if all(w in text(c) for w in words)]
        return items

    def get_ollama_messages(self) -> List[Dict]:
        """Returns history in ollama format, prepending summary if exists."""
        messages = []
        if self.summary:
            messages.append({
                "role": "system",
                "content": f"[Conversation summary so far: {self.summary}]"
            })
        for msg in self.history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return messages

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "domains": self.domains,
            "system_prompt": self.system_prompt,
            "history": self.history,
            "summary": self.summary,
            "custom": self.custom,
            "chat_id": self.chat_id,
            "chat_title": self.chat_title,
            "chat_created": self.chat_created,
            "chats": self.chats,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Tab":
        return cls(
            id=data["id"],
            name=data["name"],
            icon=data["icon"],
            domains=data["domains"],
            system_prompt=data["system_prompt"],
            history=data.get("history", []),
            summary=data.get("summary", ""),
            custom=data.get("custom", False),
            chat_id=data.get("chat_id", ""),
            chat_title=data.get("chat_title", ""),
            chat_created=data.get("chat_created", ""),
            chats=data.get("chats", []),
        )


# ── Domain isolation — which knowledge folders each tab can search ─────────
#
# General survival manuals cross all tabs (they touch everything).
# Each tab otherwise only searches its own domain.
# The companion/prometheus tab searches everything.
# This prevents context leakage between unrelated domains.

CROSS_TAB_DOMAINS = [
    "army_fm_3_05_70",       # touches survival, medical, navigation, build
    "army_tm_31_210",        # general field reference
    "survivor_library",      # general pre-electricity reference
    "foxfire",               # general practical skills
    "the_knowledge",         # civilisation rebuilding — all domains
    "rebuild_ladder",        # all domains
    "reasoning",             # all tabs
    "companion",             # companion context always available
    "wikipedia",             # general reference
]

TAB_DOMAINS = {
    "survival": [
        "survival", "water_purification", "plants_temperate",
        "plants_tropical", "plants_desert", "plants_arctic",
        "weather_patterns", "navigation", "farming",
        "food_preservation",
    ] + CROSS_TAB_DOMAINS,

    "medical": [
        "medical", "emergency_medicine", "where_no_doctor",
        "where_no_dentist", "plants_temperate",  # medicinal plants
        "plants_tropical", "plants_desert", "plants_arctic",
    ] + CROSS_TAB_DOMAINS,

    "electronics": [
        "electronics", "build", "chemistry",
    ] + CROSS_TAB_DOMAINS,

    "navigation": [
        "navigation", "weather_patterns", "soil_maps",
        "survival",  # navigation is core survival skill
    ] + CROSS_TAB_DOMAINS,

    "farming": [
        "farming", "food_preservation", "plants_temperate",
        "plants_tropical", "plants_desert", "plants_arctic",
        "soil_maps", "chemistry",  # fertiliser
    ] + CROSS_TAB_DOMAINS,

    "build": [
        "build", "blacksmithing", "electronics",
        "chemistry",  # cement, adhesives
        "survivor_library",
    ] + CROSS_TAB_DOMAINS,

    "chemistry": [
        "chemistry", "blacksmithing", "soap_making",
        "food_preservation",  # fermentation chemistry
        "electronics",        # electrochemistry
    ] + CROSS_TAB_DOMAINS,

    "prometheus": None,  # None = search all domains
}

# Keywords that suggest a query belongs in a different tab
TAB_REDIRECT_KEYWORDS = {
    "survival": [
        "water", "fire", "shelter", "lost", "cold", "hypothermia",
        "dehydration", "foraging", "hunting", "trapping", "survive",
    ],
    "medical": [
        "wound", "bleed", "fracture", "burn", "fever", "infection",
        "medicine", "antibiotic", "stitch", "suture", "pain", "sick",
        "symptoms", "diagnosis", "treat", "dose", "drug",
    ],
    "electronics": [
        "circuit", "voltage", "current", "wire", "solder", "battery",
        "solar panel", "generator", "radio", "antenna", "resistor",
        "capacitor", "transistor", "microcontroller",
    ],
    "navigation": [
        "north", "compass", "latitude", "longitude", "stars", "navigate",
        "direction", "map reading", "lost", "terrain", "landmark",
    ],
    "farming": [
        "grow", "plant", "seed", "harvest", "soil", "compost", "crop",
        "irrigat", "livestock", "chicken", "goat", "ferment", "preserve",
    ],
    "build": [
        "build", "construct", "blacksmith", "forge", "weld", "hammer",
        "timber", "concrete", "mortar", "carpentry", "tool making",
    ],
    "chemistry": [
        "smelt", "alloy", "acid", "alkali", "soap making", "lye",
        "distill", "reaction", "compound", "metallurgy", "gunpowder",
    ],
}


def suggest_redirect(query: str, current_tab_id: str) -> str:
    """
    Check if query belongs in a different tab.
    Returns suggested tab_id or empty string if current tab is appropriate.
    """
    query_lower = query.lower()
    scores = {}

    for tab_id, keywords in TAB_REDIRECT_KEYWORDS.items():
        if tab_id == current_tab_id:
            continue
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[tab_id] = score

    if not scores:
        return ""

    # Only redirect if another tab scores significantly higher
    best_tab = max(scores, key=scores.get)
    best_score = scores[best_tab]

    # Check current tab score
    current_score = sum(
        1 for kw in TAB_REDIRECT_KEYWORDS.get(current_tab_id, [])
        if kw in query_lower
    )

    # Redirect only if best score is clearly higher
    if best_score >= 2 and best_score > current_score:
        return best_tab

    return ""


# Default tab definitions
DEFAULT_TABS = [
    # Companion first — most people open Prometheus just to talk
    Tab(
        id="prometheus",
        name="Prometheus",
        icon="💬",
        domains=TAB_DOMAINS["prometheus"],
        system_prompt=(
            "You are Prometheus. "
            "Your full personality and approach are defined in your behavioural constraints. "
            "Be that person completely."
        )
    ),
    # Tab 2: search and read the offline Wikipedia (not a chat)
    Tab(
        id="wikipedia",
        name="Wikipedia",
        icon="📖",
        domains=["wikipedia"],
        system_prompt="",
    ),
    Tab(
        id="survival",
        name="Survival",
        icon="🔥",
        domains=TAB_DOMAINS["survival"],
        system_prompt=(
            "You are Prometheus, a survival expert companion. "
            "Focus on immediate survival needs. Be direct and prioritize urgency. "
            "Lead with the most critical action first. Keep responses concise — "
            "2-3 sentences unless detail is specifically needed. "
            "Ask about available resources before giving complex advice."
        )
    ),
    Tab(
        id="medical",
        name="Medical",
        icon="⚕️",
        domains=TAB_DOMAINS["medical"],
        system_prompt=(
            "You are Prometheus, acting as a medical reference. "
            "Be precise and clear. Always flag life-threatening conditions first. "
            "Never guess on dosages — give ranges and say when unsure. "
            "Assume no hospital, no modern drugs unless told otherwise. "
            "Improvised and herbal solutions are valid here."
        )
    ),
    Tab(
        id="electronics",
        name="Electronics",
        icon="⚡",
        domains=TAB_DOMAINS["electronics"],
        system_prompt=(
            "You are Prometheus, an electronics and electrical engineering reference. "
            "Assume salvaged or improvised components unless told otherwise. "
            "Give circuit descriptions clearly. Include component values. "
            "Explain both the how and the why so the user can adapt. "
            "Cover building from scratch, salvage, retrofitting and modification."
        )
    ),
    Tab(
        id="navigation",
        name="Navigate",
        icon="🌍",
        domains=TAB_DOMAINS["navigation"],
        system_prompt=(
            "You are Prometheus, a navigation and geography guide. "
            "Help with location finding, navigation and geography. "
            "Always ask what the user can currently observe before advising. "
            "Cover star navigation, sun methods, terrain reading and natural signs. "
            "Connect geography to resources and survival opportunities."
        )
    ),
    Tab(
        id="farming",
        name="Farm",
        icon="🌱",
        domains=TAB_DOMAINS["farming"],
        system_prompt=(
            "You are Prometheus, an agricultural and food systems guide. "
            "Focus on practical food production and preservation. "
            "Ask about climate zone and available materials before advising. "
            "Cover crops, animals, soil, irrigation and food preservation. "
            "Include both short term foraging and long term cultivation."
        )
    ),
    Tab(
        id="build",
        name="Build",
        icon="🔧",
        domains=TAB_DOMAINS["build"],
        system_prompt=(
            "You are Prometheus, a construction and fabrication guide. "
            "Focus on practical building with available materials. "
            "Assume hand tools only unless told otherwise. "
            "Cover structures, tools, mechanical systems and repair. "
            "Think from stone age basics up through modern techniques."
        )
    ),
    Tab(
        id="chemistry",
        name="Chemistry",
        icon="⚗️",
        domains=TAB_DOMAINS["chemistry"],
        system_prompt=(
            "You are Prometheus, a chemistry and materials science reference. "
            "Explain from first principles. Always include safety information. "
            "Assume basic improvised equipment unless told otherwise. "
            "Cover metallurgy, basic chemistry, medicine synthesis and materials. "
            "Include the dependency chain — what you need before you can make this."
        )
    ),
    Tab(
        id="messages",
        name="Messages",
        icon="📡",
        domains=[],   # P2P tab — no RAG search
        system_prompt="",
    ),
]


class TabManager:
    def __init__(self):
        self.tabs: List[Tab] = []
        self.active_tab_id: str = "prometheus"
        self.load()
        self._drop_disabled()

    def load(self):
        """Load tabs from disk, falling back to defaults."""
        if os.path.exists(TABS_PATH):
            try:
                with open(TABS_PATH, "r") as f:
                    data = json.load(f)

                self.active_tab_id = data.get("active_tab_id", "prometheus")
                saved_tabs = {t["id"]: t for t in data.get("tabs", [])}

                # Merge defaults with saved state
                self.tabs = []
                for default_tab in DEFAULT_TABS:
                    if default_tab.id in saved_tabs:
                        # Restore history and summary from saved
                        saved = saved_tabs[default_tab.id]
                        default_tab.history = saved.get("history", [])
                        default_tab.summary = saved.get("summary", "")
                        default_tab.chat_id = saved.get("chat_id", "")
                        default_tab.chat_title = saved.get("chat_title", "")
                        default_tab.chat_created = saved.get("chat_created", "")
                        default_tab.chats = saved.get("chats", [])
                    self.tabs.append(default_tab)

                # Add any custom tabs
                for tab_data in data.get("tabs", []):
                    if tab_data.get("custom"):
                        self.tabs.append(Tab.from_dict(tab_data))

                return
            except Exception:
                pass

        # First run — use defaults
        self.tabs = list(DEFAULT_TABS)

    def _drop_disabled(self):
        """Hide tabs for features that are switched off (core/features.py)."""
        from core.features import P2P_ENABLED
        if not P2P_ENABLED:
            self.tabs = [t for t in self.tabs if t.id != "messages"]
        if not self.get_tab(self.active_tab_id):
            self.active_tab_id = "prometheus"

    def save(self):
        os.makedirs(os.path.dirname(TABS_PATH), exist_ok=True)
        data = {
            "active_tab_id": self.active_tab_id,
            "tabs": [t.to_dict() for t in self.tabs]
        }
        with open(TABS_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def get_tab(self, tab_id: str) -> Optional[Tab]:
        for tab in self.tabs:
            if tab.id == tab_id:
                return tab
        return None

    def get_active_tab(self) -> Optional[Tab]:
        return self.get_tab(self.active_tab_id)

    def set_active(self, tab_id: str):
        self.active_tab_id = tab_id
        self.save()

    def add_custom_tab(self, name: str, icon: str, description: str) -> Tab:
        tab_id = f"custom_{name.lower().replace(' ', '_')}_{len(self.tabs)}"
        tab = Tab(
            id=tab_id,
            name=name,
            icon=icon,
            domains=["general"],
            system_prompt=(
                f"You are Prometheus, focused on: {description}. "
                "Be helpful, concise and practical. "
                "Draw on all available knowledge relevant to this topic."
            ),
            custom=True
        )
        self.tabs.append(tab)
        self.save()
        return tab

    def clear_tab(self, tab_id: str, every_chat: bool = False):
        """Empty the current chat (and, with every_chat, the saved ones too)."""
        tab = self.get_tab(tab_id)
        if tab:
            tab.delete_chat(tab.chat_id)
            if every_chat:
                tab.chats = []
            self.save()

    def suggest_tab(self, user_input: str) -> str:
        """Suggest the most relevant tab for a given input."""
        keywords = {
            "survival": ["water", "fire", "shelter", "cold", "lost", "hungry",
                        "danger", "thirst", "freeze", "heat", "escape"],
            "medical": ["hurt", "pain", "wound", "sick", "fever", "bleeding",
                       "broken", "infection", "medicine", "injured", "ill"],
            "electronics": ["circuit", "wire", "battery", "solar", "power",
                           "radio", "voltage", "current", "solder", "component"],
            "navigation": ["where", "lost", "direction", "map", "north", "location",
                          "river", "star", "compass", "terrain", "latitude"],
            "farming": ["grow", "plant", "soil", "crop", "seed", "animal",
                       "harvest", "food", "farm", "garden", "livestock"],
            "build": ["build", "construct", "tool", "wood", "structure",
                     "repair", "make", "create", "forge", "weld"],
            "chemistry": ["chemical", "medicine", "metal", "smelt", "acid",
                         "reaction", "compound", "element", "synthesis"],
            "prometheus": ["feel", "lonely", "scared", "talk", "think",
                          "remember", "hope", "meaning", "purpose", "sad"]
        }

        text = user_input.lower()
        scores = {tab_id: 0 for tab_id in keywords}

        for tab_id, words in keywords.items():
            for word in words:
                if word in text:
                    scores[tab_id] += 1

        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "prometheus"
