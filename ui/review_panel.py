"""
Review tab — what Prometheus thinks you've told it about yourself, waiting
for you to confirm. Nothing here is used until you accept it.

Each card: what it understood ("Kate is your sister"), the words it came
from, and Accept / Edit / Reject. Edit lets you correct the value, then
saves it as accepted. Reject means it's never used or raised again.
The same on desktop and phone (cards stack; buttons wrap under the text).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal

from core import claims
from core.platform_info import PHONE_LAYOUT

_SURE = ((0.8, "sure"), (0.65, "fairly sure"), (0.0, "not sure"))


def _how_sure(confidence: float) -> str:
    return next(label for limit, label in _SURE if confidence >= limit)


class _ClaimCard(QFrame):
    """One claim. Emits done() after Accept / Save / Reject."""
    done = Signal()

    def __init__(self, claim: claims.Claim, memory, parent=None):
        super().__init__(parent)
        self.claim, self.memory = claim, memory
        self.setObjectName("claimCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Step 1: what it understood, and from what
        label, _ = claims.FIELDS.get(claim.field, ("About you", True))
        kind = QLabel(f"{label} · {_how_sure(claim.confidence)}")
        kind.setObjectName("claimKind")
        lay.addWidget(kind)
        what = QLabel(claim.note[:1].upper() + claim.note[1:])
        what.setObjectName("claimWhat")
        what.setWordWrap(True)
        lay.addWidget(what)
        said = QLabel(f"You said: “{claim.utterance}”")
        said.setObjectName("claimSaid")
        said.setWordWrap(True)
        lay.addWidget(said)

        # Step 2: the edit box (hidden until Edit)
        self._edit = QLineEdit(claim.value)
        self._edit.setObjectName("claimEdit")
        self._edit.returnPressed.connect(self._save_edit)
        self._edit.hide()
        lay.addWidget(self._edit)

        # Step 3: the choices
        row = QHBoxLayout()
        row.setSpacing(8)
        self._accept = QPushButton("Accept")
        self._accept.setObjectName("primaryBtn")
        self._accept.clicked.connect(self._do_accept)
        self._editbtn = QPushButton("Edit")
        self._editbtn.clicked.connect(self._start_edit)
        reject = QPushButton("Reject")
        reject.setObjectName("quietBtn")
        reject.clicked.connect(self._do_reject)
        for b in (self._accept, self._editbtn, reject):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

    def _start_edit(self):
        self._edit.show()
        self._edit.setFocus()
        self._edit.selectAll()
        self._accept.setText("Save")
        self._accept.clicked.disconnect()
        self._accept.clicked.connect(self._save_edit)
        self._editbtn.hide()

    def _save_edit(self):
        claims.accept(self.claim.id, self.memory, edited_value=self._edit.text())
        self.done.emit()

    def _do_accept(self):
        claims.accept(self.claim.id, self.memory)
        self.done.emit()

    def _do_reject(self):
        claims.reject(self.claim.id)
        self.done.emit()


class ReviewPanel(QWidget):
    changed = Signal(int)          # how many are still waiting

    def __init__(self, memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setObjectName("reviewPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("reviewScroll")
        outer.addWidget(scroll)

        body = QWidget()
        body.setObjectName("reviewBody")
        scroll.setWidget(body)
        self._lay = QVBoxLayout(body)
        m = 16 if PHONE_LAYOUT else 32
        self._lay.setContentsMargins(m, 24, m, 24)
        self._lay.setSpacing(12)

        title = QLabel("Things to confirm")
        title.setObjectName("reviewTitle")
        self._lay.addWidget(title)
        intro = QLabel("What you've said about yourself, waiting for you. "
                       "Nothing here is used until you accept it.")
        intro.setObjectName("reviewIntro")
        intro.setWordWrap(True)
        self._lay.addWidget(intro)

        self._cards = QVBoxLayout()
        self._cards.setSpacing(10)
        self._lay.addLayout(self._cards)

        self._empty = QLabel("Nothing to confirm right now. When you mention something about "
                             "yourself — your sister's name, where you live, what you like — "
                             "it shows up here first.")
        self._empty.setObjectName("reviewEmpty")
        self._empty.setWordWrap(True)
        self._lay.addWidget(self._empty)

        self._accept_all = QPushButton("Accept all")
        self._accept_all.setObjectName("quietBtn")
        self._accept_all.setCursor(Qt.PointingHandCursor)
        self._accept_all.setFixedHeight(34)
        self._accept_all.clicked.connect(self._do_accept_all)
        self._lay.addWidget(self._accept_all, 0, Qt.AlignLeft)
        self._lay.addStretch()
        self.refresh()

    def refresh(self):
        """Rebuild the cards from what's pending."""
        while self._cards.count():
            item = self._cards.takeAt(0)
            card = item.widget()
            if card:
                card.setParent(None)               # gone now, not after the next event loop
                card.deleteLater()
        waiting = claims.pending()
        for c in waiting:
            card = _ClaimCard(c, self.memory)
            card.done.connect(self.refresh)
            self._cards.addWidget(card)
        self._empty.setVisible(not waiting)
        self._accept_all.setVisible(len(waiting) > 1)
        self.changed.emit(len(waiting))

    def _do_accept_all(self):
        for c in claims.pending():
            claims.accept(c.id, self.memory)
        self.refresh()
