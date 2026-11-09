"""
P2P Messaging System
====================
Peer-to-peer communication between Prometheus nodes.
No internet required. Works on local WiFi, direct connections.

Phase 1: UDP broadcast discovery + TCP messaging
Phase 2: Bluetooth (future)
Phase 3: LoRa long range (future, optional hardware)
"""

import json
import time
import uuid
import socket
import hashlib
import threading
import queue
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime


# ── Constants ──────────────────────────────────────────────────────────────

DISCOVERY_PORT  = 42000
MESSAGING_PORT  = 42001
BROADCAST_ADDR  = '<broadcast>'
PROTOCOL_SIG    = b"PRO1"
DISCOVERY_INTERVAL = 30      # seconds between presence broadcasts
NODE_TIMEOUT    = 120        # seconds before a node is considered offline
IDENTITY_PATH   = Path("memory/node_identity.json")


# ── Message types ──────────────────────────────────────────────────────────

class MsgType(Enum):
    # Presence
    PING        = "ping"        # I exist
    PONG        = "pong"        # I see you

    # Communication
    TEXT        = "text"        # direct message
    BROADCAST   = "broadcast"   # to all nodes

    # Situation
    STATUS      = "status"      # alive/injured/needs_help
    ALERT       = "alert"       # danger warning
    RESOURCE    = "resource"    # have/need resources

    # Knowledge
    DISCOVERY   = "discovery"   # local finding worth sharing
    SYNC_REQ    = "sync_req"    # request knowledge update
    SYNC_DATA   = "sync_data"   # knowledge chunk


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class NodeInfo:
    node_id:    str
    name:       str
    location:   str
    status:     str
    day:        int
    last_seen:  float
    address:    str           # IP address
    trusted:    bool = False

    def is_online(self) -> bool:
        return time.time() - self.last_seen < NODE_TIMEOUT

    def time_ago(self) -> str:
        secs = int(time.time() - self.last_seen)
        if secs < 60:    return f"{secs}s ago"
        if secs < 3600:  return f"{secs//60}m ago"
        return f"{secs//3600}h ago"


@dataclass
class Message:
    msg_id:     str
    msg_type:   str
    sender_id:  str
    sender_name: str
    timestamp:  float
    payload:    dict
    inbound:    bool = True   # True = received, False = sent

    def formatted_time(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M")

    def display_text(self) -> str:
        t = self.msg_type
        p = self.payload
        if t in (MsgType.TEXT.value, MsgType.BROADCAST.value):
            return p.get("text", "")
        if t == MsgType.ALERT.value:
            return f"⚠ ALERT: {p.get('text', '')}"
        if t == MsgType.STATUS.value:
            return (f"Status: {p.get('condition', 'unknown')} | "
                    f"{p.get('group_size', 1)} person(s) | "
                    f"{p.get('location', 'unknown location')}")
        if t == MsgType.RESOURCE.value:
            have = ", ".join(p.get("have", []))
            need = ", ".join(p.get("need", []))
            parts = []
            if have: parts.append(f"Has: {have}")
            if need: parts.append(f"Needs: {need}")
            return " | ".join(parts)
        if t == MsgType.DISCOVERY.value:
            return f"📍 Discovery: {p.get('summary', '')}"
        return json.dumps(p)


# ── Node identity ──────────────────────────────────────────────────────────

class NodeIdentity:
    """Persistent node ID. Generated once, saved forever."""

    def __init__(self):
        self.node_id   = ""
        self.name      = "Unknown"
        self._load()

    def _load(self):
        if IDENTITY_PATH.exists():
            try:
                data = json.loads(IDENTITY_PATH.read_text())
                self.node_id = data.get("node_id", "")
                self.name    = data.get("name", "Unknown")
                if self.node_id:
                    return
            except Exception:
                pass
        # Generate new identity
        self.node_id = str(uuid.uuid4())[:8].upper()
        self._save()

    def _save(self):
        IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        IDENTITY_PATH.write_text(json.dumps({
            "node_id": self.node_id,
            "name":    self.name,
        }, indent=2))

    def set_name(self, name: str):
        self.name = name
        self._save()


# ── Message store ──────────────────────────────────────────────────────────

class MessageStore:
    """Persistent message history."""

    STORE_PATH = Path("memory/p2p_messages.json")
    MAX_MESSAGES = 500

    def __init__(self):
        self._messages: List[Message] = []
        self._seen_ids: set = set()
        self._load()

    def _load(self):
        if self.STORE_PATH.exists():
            try:
                data = json.loads(self.STORE_PATH.read_text())
                for m in data:
                    msg = Message(**m)
                    self._messages.append(msg)
                    self._seen_ids.add(msg.msg_id)
            except Exception:
                pass

    def save(self):
        self.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Keep last MAX_MESSAGES
        recent = self._messages[-self.MAX_MESSAGES:]
        self.STORE_PATH.write_text(json.dumps(
            [asdict(m) for m in recent], indent=2
        ))

    def add(self, msg: Message) -> bool:
        """Add message. Returns False if duplicate."""
        if msg.msg_id in self._seen_ids:
            return False
        self._seen_ids.add(msg.msg_id)
        self._messages.append(msg)
        self.save()
        return True

    def already_seen(self, msg_id: str) -> bool:
        return msg_id in self._seen_ids

    def all_messages(self) -> List[Message]:
        return list(self._messages)

    def messages_with(self, node_id: str) -> List[Message]:
        return [m for m in self._messages
                if m.sender_id == node_id or
                (not m.inbound and m.payload.get("to") == node_id)]

    def broadcasts(self) -> List[Message]:
        return [m for m in self._messages
                if m.msg_type == MsgType.BROADCAST.value]


# ── P2P Engine ─────────────────────────────────────────────────────────────

class P2PEngine:
    """
    Core P2P networking engine.
    Handles discovery, messaging, and knowledge sync.
    """

    def __init__(self, memory):
        self.memory    = memory
        self.identity  = NodeIdentity()
        self.store     = MessageStore()
        self._nodes:   Dict[str, NodeInfo] = {}
        self._running  = False
        self._callbacks: List[Callable] = []

        # Set name from memory if available
        name = memory.data["user"].get("name")
        if name:
            self.identity.set_name(name)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True

        # Discovery listener
        threading.Thread(
            target=self._listen_discovery,
            daemon=True, name="p2p_discovery"
        ).start()

        # Message listener
        threading.Thread(
            target=self._listen_messages,
            daemon=True, name="p2p_messages"
        ).start()

        # Presence broadcaster
        threading.Thread(
            target=self._broadcast_loop,
            daemon=True, name="p2p_broadcast"
        ).start()

    def stop(self):
        self._running = False

    def on_message(self, callback: Callable):
        """Register callback for incoming messages."""
        self._callbacks.append(callback)

    # ── Discovery ──────────────────────────────────────────────────────────

    def _broadcast_loop(self):
        """Broadcast presence every DISCOVERY_INTERVAL seconds."""
        while self._running:
            self._broadcast_ping()
            time.sleep(DISCOVERY_INTERVAL)

    def _broadcast_ping(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2)

            payload = self._make_packet(MsgType.PING, {
                "name":     self.identity.name,
                "location": self.memory.data["user"].get("location_estimate", ""),
                "status":   "online",
                "day":      self.memory.data["user"].get("day_count", 1),
                "port":     MESSAGING_PORT,
            })

            sock.sendto(payload, (BROADCAST_ADDR, DISCOVERY_PORT))
            sock.close()
        except Exception:
            pass

    def _listen_discovery(self):
        """Listen for other nodes broadcasting their presence."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', DISCOVERY_PORT))
            sock.settimeout(1.0)

            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    self._handle_discovery(data, addr[0])
                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception:
            pass

    def _handle_discovery(self, data: bytes, addr: str):
        if not data.startswith(PROTOCOL_SIG):
            return

        try:
            packet = json.loads(data[4:].decode())
            sender_id = packet.get("sender_id", "")
            if sender_id == self.identity.node_id:
                return  # Our own broadcast

            p = packet.get("payload", {})
            node = NodeInfo(
                node_id   = sender_id,
                name      = p.get("name", f"Node_{sender_id}"),
                location  = p.get("location", ""),
                status    = p.get("status", "online"),
                day       = p.get("day", 1),
                last_seen = time.time(),
                address   = addr,
                trusted   = self._nodes.get(sender_id, NodeInfo(
                    sender_id, "", "", "", 0, 0, ""
                )).trusted if sender_id in self._nodes else False,
            )
            self._nodes[sender_id] = node

            # Send pong back
            self._send_direct(addr, p.get("port", MESSAGING_PORT),
                              MsgType.PONG, {
                                  "name":     self.identity.name,
                                  "location": self.memory.data["user"].get("location_estimate", ""),
                                  "status":   "online",
                                  "day":      self.memory.data["user"].get("day_count", 1),
                              })

            # Notify UI
            self._notify(Message(
                msg_id      = packet.get("msg_id", ""),
                msg_type    = MsgType.PING.value,
                sender_id   = sender_id,
                sender_name = node.name,
                timestamp   = time.time(),
                payload     = p,
                inbound     = True,
            ))

        except Exception:
            pass

    # ── Messaging ──────────────────────────────────────────────────────────

    def _listen_messages(self):
        """Listen for incoming direct messages."""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('', MESSAGING_PORT))
            server.listen(5)
            server.settimeout(1.0)

            while self._running:
                try:
                    conn, addr = server.accept()
                    threading.Thread(
                        target=self._handle_connection,
                        args=(conn, addr[0]),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception:
            pass

    def _handle_connection(self, conn, addr: str):
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            conn.close()

            if not data.startswith(PROTOCOL_SIG):
                return

            packet = json.loads(data[4:].decode())
            sender_id = packet.get("sender_id", "")

            if self.store.already_seen(packet.get("msg_id", "")):
                return

            msg = Message(
                msg_id      = packet.get("msg_id", ""),
                msg_type    = packet.get("msg_type", ""),
                sender_id   = sender_id,
                sender_name = self._nodes.get(sender_id, NodeInfo(
                    sender_id, f"Node_{sender_id}", "", "", 0, 0, addr
                )).name,
                timestamp   = packet.get("timestamp", time.time()),
                payload     = packet.get("payload", {}),
                inbound     = True,
            )

            if self.store.add(msg):
                self._notify(msg)

                # Handle knowledge discovery
                if msg.msg_type == MsgType.DISCOVERY.value:
                    self._ingest_discovery(msg)

        except Exception:
            pass

    def _send_direct(self, addr: str, port: int,
                     msg_type: MsgType, payload: dict):
        """Send a message directly to a node."""
        try:
            packet = self._make_packet(msg_type, payload)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((addr, port))
            sock.sendall(packet)
            sock.close()
            return True
        except Exception:
            return False

    # ── Public API ─────────────────────────────────────────────────────────

    def send_text(self, to_node_id: str, text: str) -> bool:
        """Send a direct text message to a specific node."""
        node = self._nodes.get(to_node_id)
        if not node:
            return False

        msg_id = self._new_id()
        payload = {"text": text, "to": to_node_id}

        sent = self._send_direct(
            node.address, MESSAGING_PORT, MsgType.TEXT, payload
        )

        if sent:
            msg = Message(
                msg_id      = msg_id,
                msg_type    = MsgType.TEXT.value,
                sender_id   = self.identity.node_id,
                sender_name = self.identity.name,
                timestamp   = time.time(),
                payload     = payload,
                inbound     = False,
            )
            self.store.add(msg)

        return sent

    def broadcast_text(self, text: str):
        """Broadcast a text message to all nodes."""
        msg_id = self._new_id()
        payload = {"text": text}

        for node in self.online_nodes():
            self._send_direct(
                node.address, MESSAGING_PORT, MsgType.BROADCAST, payload
            )

        msg = Message(
            msg_id      = msg_id,
            msg_type    = MsgType.BROADCAST.value,
            sender_id   = self.identity.node_id,
            sender_name = self.identity.name,
            timestamp   = time.time(),
            payload     = payload,
            inbound     = False,
        )
        self.store.add(msg)

    def send_alert(self, text: str):
        """Broadcast an emergency alert to all nodes."""
        payload = {"text": text, "severity": "high"}
        for node in self.online_nodes():
            self._send_direct(
                node.address, MESSAGING_PORT, MsgType.ALERT, payload
            )
        msg = Message(
            msg_id      = self._new_id(),
            msg_type    = MsgType.ALERT.value,
            sender_id   = self.identity.node_id,
            sender_name = self.identity.name,
            timestamp   = time.time(),
            payload     = payload,
            inbound     = False,
        )
        self.store.add(msg)

    def send_status(self, condition: str, group_size: int, location: str):
        """Broadcast current status to all nodes."""
        payload = {
            "condition":  condition,
            "group_size": group_size,
            "location":   location,
            "day":        self.memory.data["user"].get("day_count", 1),
        }
        for node in self.online_nodes():
            self._send_direct(
                node.address, MESSAGING_PORT, MsgType.STATUS, payload
            )

    def share_resources(self, have: List[str], need: List[str]):
        """Broadcast resource availability/needs."""
        payload = {"have": have, "need": need}
        for node in self.online_nodes():
            self._send_direct(
                node.address, MESSAGING_PORT, MsgType.RESOURCE, payload
            )

    def share_discovery(self, summary: str, full_text: str, location: str):
        """Share a local discovery with the network."""
        payload = {
            "summary":   summary,
            "full_text": full_text,
            "location":  location,
        }
        for node in self.online_nodes():
            self._send_direct(
                node.address, MESSAGING_PORT, MsgType.DISCOVERY, payload
            )

    def trust_node(self, node_id: str):
        if node_id in self._nodes:
            self._nodes[node_id].trusted = True

    def online_nodes(self) -> List[NodeInfo]:
        return [n for n in self._nodes.values() if n.is_online()]

    def all_nodes(self) -> List[NodeInfo]:
        return list(self._nodes.values())

    def node_count(self) -> int:
        return len(self.online_nodes())

    # ── Knowledge ingestion ────────────────────────────────────────────────

    def _ingest_discovery(self, msg: Message):
        """Add peer discovery to personal knowledge base."""
        try:
            p = msg.payload
            content = (
                f"[PEER REPORT from {msg.sender_name} — "
                f"unverified, day {self.memory.data['user'].get('day_count', 1)}]\n"
                f"Location: {p.get('location', 'unknown')}\n\n"
                f"{p.get('full_text', p.get('summary', ''))}"
            )
            dest = Path("memory/personal_docs") / f"peer_{msg.msg_id}.txt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        except Exception:
            pass

    # ── Utilities ──────────────────────────────────────────────────────────

    def _make_packet(self, msg_type: MsgType, payload: dict) -> bytes:
        packet = json.dumps({
            "msg_id":    self._new_id(),
            "msg_type":  msg_type.value,
            "sender_id": self.identity.node_id,
            "timestamp": time.time(),
            "payload":   payload,
        }).encode()
        return PROTOCOL_SIG + packet

    def _new_id(self) -> str:
        return hashlib.md5(
            f"{self.identity.node_id}{time.time()}".encode()
        ).hexdigest()[:12]

    def _notify(self, msg: Message):
        for cb in self._callbacks:
            try:
                cb(msg)
            except Exception:
                pass
