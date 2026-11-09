"""
Messages View
=============
P2P messaging interface.
Shows online nodes, message history, quick action buttons.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QListWidget,
    QListWidgetItem, QTextEdit, QLineEdit, QSplitter,
    QSizePolicy, QDialog, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from core.app.p2p import P2PEngine, Message, NodeInfo, MsgType


# ── Node list item ─────────────────────────────────────────────────────────

class NodeItem(QListWidgetItem):
    def __init__(self, node: NodeInfo):
        super().__init__()
        self.node_id = node.node_id
        self.update_from(node)

    def update_from(self, node: NodeInfo):
        status = "●" if node.is_online() else "○"
        trusted = " ✓" if node.trusted else ""
        self.setText(
            f"{status} {node.name}{trusted}\n"
            f"  {node.location or 'Unknown location'}  "
            f"Day {node.day}  {node.time_ago()}"
        )
        color = QColor("#4a8a4a") if node.is_online() else QColor("#666")
        self.setForeground(color)


# ── Message bubble ─────────────────────────────────────────────────────────

class MessageBubble(QFrame):
    def __init__(self, msg: Message, parent=None):
        super().__init__(parent)
        self.setObjectName(
            "bubble_user" if not msg.inbound else "bubble_assistant"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        is_alert = msg.msg_type == MsgType.ALERT.value

        text = msg.display_text()
        time_str = msg.formatted_time()
        name = "" if not msg.inbound else f"{msg.sender_name}: "

        if is_alert:
            self.setObjectName("alertMessage")   # red bar on the edge, neutral text

        label = QLabel(f"{name}{text}")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        time_label = QLabel(time_str)
        time_label.setObjectName("infoLabel")
        time_label.setFixedWidth(40)
        time_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        if msg.inbound:
            layout.addWidget(label)
            layout.addWidget(time_label)
        else:
            layout.addWidget(time_label)
            layout.addWidget(label)


# ── Main messages widget ───────────────────────────────────────────────────

class MessagesWidget(QWidget):

    def __init__(self, p2p: P2PEngine, parent=None):
        super().__init__(parent)
        self.p2p = p2p
        self._active_node_id: str = ""   # empty = broadcast view
        self._setup_ui()

        # Register for incoming messages
        self.p2p.on_message(self._on_message_received)

        # Refresh node list periodically
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_nodes)
        self._refresh_timer.start(5000)

        self._refresh_nodes()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(50)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("📡 Network Messages")
        title.setObjectName("headerTitle")
        font = title.font()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)

        self._node_count = QLabel("Scanning...")
        self._node_count.setObjectName("assessmentProgress")

        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(self._node_count)
        layout.addWidget(header)

        # Main split: node list | messages
        splitter = QSplitter(Qt.Horizontal)

        # ── Left: node list ────────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("sidebar")
        left.setMinimumWidth(200)
        left.setMaximumWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        nodes_label = QLabel("  NODES ONLINE")
        nodes_label.setObjectName("sectionHeader")
        left_layout.addWidget(nodes_label)

        self._node_list = QListWidget()
        self._node_list.setObjectName("docList")
        self._node_list.currentItemChanged.connect(self._on_node_selected)

        # "All / Broadcast" option at top
        all_item = QListWidgetItem("📢 Broadcast (all nodes)")
        all_item.setData(Qt.UserRole, "")
        self._node_list.addItem(all_item)

        left_layout.addWidget(self._node_list)

        # Quick action buttons
        actions = QFrame()
        actions.setObjectName("inputBar")
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(6)

        alert_btn = QPushButton("⚠ Send Alert")
        alert_btn.setObjectName("navBtn")
        alert_btn.clicked.connect(self._send_alert_dialog)

        status_btn = QPushButton("📊 Share Status")
        status_btn.setObjectName("navBtn")
        status_btn.clicked.connect(self._send_status_dialog)

        resource_btn = QPushButton("📦 Share Resources")
        resource_btn.setObjectName("navBtn")
        resource_btn.clicked.connect(self._send_resource_dialog)

        discovery_btn = QPushButton("📍 Share Discovery")
        discovery_btn.setObjectName("navBtn")
        discovery_btn.clicked.connect(self._send_discovery_dialog)

        for btn in (alert_btn, status_btn, resource_btn, discovery_btn):
            actions_layout.addWidget(btn)

        left_layout.addWidget(actions)
        splitter.addWidget(left)

        # ── Right: message view ────────────────────────────────────────────
        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Conversation header
        self._conv_header = QLabel("  📢 Broadcast — all nodes")
        self._conv_header.setObjectName("tabInfo")
        self._conv_header.setFixedHeight(32)
        right_layout.addWidget(self._conv_header)

        # Messages scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("chatScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._msgs_widget = QWidget()
        self._msgs_widget.setObjectName("messagesWidget")
        self._msgs_layout = QVBoxLayout(self._msgs_widget)
        self._msgs_layout.setContentsMargins(8, 8, 8, 8)
        self._msgs_layout.setSpacing(6)
        self._msgs_layout.addStretch()

        scroll.setWidget(self._msgs_widget)
        self._scroll = scroll
        right_layout.addWidget(scroll)

        # Input row
        input_frame = QFrame()
        input_frame.setObjectName("inputBar")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type message...")
        self._input.returnPressed.connect(self._send_text)

        send_btn = QPushButton("➤")
        send_btn.setObjectName("sendBtn")
        send_btn.setFixedSize(44, 44)
        send_btn.clicked.connect(self._send_text)

        input_layout.addWidget(self._input)
        input_layout.addWidget(send_btn)
        right_layout.addWidget(input_frame)

        splitter.addWidget(right)
        splitter.setSizes([220, 580])
        layout.addWidget(splitter)

    # ── Node management ────────────────────────────────────────────────────

    def _refresh_nodes(self):
        nodes = self.p2p.online_nodes()
        self._node_count.setText(
            f"{len(nodes)} node{'s' if len(nodes) != 1 else ''} online"
        )

        # Update existing items, add new ones
        existing_ids = set()
        for i in range(1, self._node_list.count()):  # skip broadcast item
            item = self._node_list.item(i)
            if item:
                nid = item.data(Qt.UserRole)
                existing_ids.add(nid)
                # Update if node still exists
                node = next((n for n in nodes if n.node_id == nid), None)
                if node and isinstance(item, NodeItem):
                    item.update_from(node)

        # Add new nodes
        for node in nodes:
            if node.node_id not in existing_ids:
                item = NodeItem(node)
                item.setData(Qt.UserRole, node.node_id)
                self._node_list.addItem(item)

    def _on_node_selected(self, current, previous):
        if not current:
            return
        node_id = current.data(Qt.UserRole)
        self._active_node_id = node_id or ""

        if node_id:
            node = next(
                (n for n in self.p2p.all_nodes() if n.node_id == node_id),
                None
            )
            name = node.name if node else node_id
            self._conv_header.setText(f"  💬 {name}")
            messages = self.p2p.store.messages_with(node_id)
        else:
            self._conv_header.setText("  📢 Broadcast — all nodes")
            messages = self.p2p.store.broadcasts()

        self._load_messages(messages)

    def _load_messages(self, messages):
        # Clear
        while self._msgs_layout.count() > 1:
            item = self._msgs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for msg in messages[-50:]:  # last 50
            if msg.msg_type in (
                MsgType.PING.value, MsgType.PONG.value
            ):
                continue
            bubble = MessageBubble(msg)
            self._msgs_layout.insertWidget(
                self._msgs_layout.count() - 1, bubble
            )

        QTimer.singleShot(50, self._scroll_bottom)

    def _on_message_received(self, msg: Message):
        """Called from P2P engine when a message arrives."""
        # Refresh regardless — update node list and potentially message view
        QTimer.singleShot(0, self._refresh_nodes)

        # Only update message view if relevant to current conversation
        if msg.msg_type in (MsgType.PING.value, MsgType.PONG.value):
            return

        show = (
            (self._active_node_id == "" and
             msg.msg_type in (MsgType.BROADCAST.value, MsgType.ALERT.value,
                              MsgType.STATUS.value, MsgType.RESOURCE.value,
                              MsgType.DISCOVERY.value))
            or
            (self._active_node_id == msg.sender_id)
        )

        if show:
            QTimer.singleShot(0, lambda: self._add_bubble(msg))

    def _add_bubble(self, msg: Message):
        bubble = MessageBubble(msg)
        self._msgs_layout.insertWidget(
            self._msgs_layout.count() - 1, bubble
        )
        self._scroll_bottom()

    def _scroll_bottom(self):
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    # ── Sending ────────────────────────────────────────────────────────────

    def _send_text(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()

        if self._active_node_id:
            self.p2p.send_text(self._active_node_id, text)
        else:
            self.p2p.broadcast_text(text)

        # Refresh messages
        self._on_node_selected(self._node_list.currentItem(), None)

    def _send_alert_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Send Emergency Alert")
        dialog.setFixedSize(400, 180)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Alert message (sent to ALL nodes):"))
        text_input = QLineEdit()
        text_input.setPlaceholderText("e.g. Flood approaching from north, move to high ground")
        layout.addWidget(text_input)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        send = QPushButton("⚠ Send Alert")
        send.setObjectName("dangerBtn")
        send.clicked.connect(lambda: (
            self.p2p.send_alert(text_input.text()),
            dialog.accept()
        ))
        btns.addWidget(cancel)
        btns.addWidget(send)
        layout.addLayout(btns)
        dialog.exec()

    def _send_status_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Share Status")
        dialog.setFixedSize(400, 220)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Condition:"))
        condition = QComboBox()
        condition.addItems(["OK", "Injured (minor)", "Injured (serious)",
                            "Sick", "Low on supplies", "Needs help"])
        layout.addWidget(condition)

        layout.addWidget(QLabel("Group size:"))
        size_input = QLineEdit("1")
        layout.addWidget(size_input)

        layout.addWidget(QLabel("Location:"))
        from core.you.memory import Memory
        loc = self.p2p.memory.data["user"].get("location_estimate", "")
        loc_input = QLineEdit(loc)
        layout.addWidget(loc_input)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        send = QPushButton("Send Status")
        send.setObjectName("primaryBtn")

        def do_send():
            try:
                size = int(size_input.text())
            except ValueError:
                size = 1
            self.p2p.send_status(
                condition.currentText(), size, loc_input.text()
            )
            dialog.accept()

        send.clicked.connect(do_send)
        btns.addWidget(cancel)
        btns.addWidget(send)
        layout.addLayout(btns)
        dialog.exec()

    def _send_resource_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Share Resources")
        dialog.setFixedSize(400, 200)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        layout.addWidget(QLabel("I have (comma separated):"))
        have_input = QLineEdit()
        have_input.setPlaceholderText("e.g. antibiotics, tools, food")
        layout.addWidget(have_input)

        layout.addWidget(QLabel("I need (comma separated):"))
        need_input = QLineEdit()
        need_input.setPlaceholderText("e.g. water, shelter, medical help")
        layout.addWidget(need_input)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        send = QPushButton("Share")
        send.setObjectName("primaryBtn")

        def do_send():
            have = [x.strip() for x in have_input.text().split(",") if x.strip()]
            need = [x.strip() for x in need_input.text().split(",") if x.strip()]
            self.p2p.share_resources(have, need)
            dialog.accept()

        send.clicked.connect(do_send)
        btns.addWidget(cancel)
        btns.addWidget(send)
        layout.addLayout(btns)
        dialog.exec()

    def _send_discovery_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Share Discovery")
        dialog.setMinimumSize(420, 260)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Summary (one line):"))
        summary_input = QLineEdit()
        summary_input.setPlaceholderText("e.g. Clean water spring found")
        layout.addWidget(summary_input)

        layout.addWidget(QLabel("Details:"))
        detail_input = QTextEdit()
        detail_input.setPlaceholderText(
            "e.g. Spring at base of north ridge, tested clean, flowing well. "
            "Approximately 2km north of camp."
        )
        detail_input.setFixedHeight(80)
        layout.addWidget(detail_input)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        send = QPushButton("Share Discovery")
        send.setObjectName("primaryBtn")

        def do_send():
            loc = self.p2p.memory.data["user"].get("location_estimate", "")
            self.p2p.share_discovery(
                summary_input.text(),
                detail_input.toPlainText(),
                loc
            )
            dialog.accept()

        send.clicked.connect(do_send)
        btns.addWidget(cancel)
        btns.addWidget(send)
        layout.addLayout(btns)
        dialog.exec()
