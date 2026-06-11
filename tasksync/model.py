"""The canonical task model shared by every connector.

Connectors translate their native representation (a Jira issue, a Trello
card, a CalDAV VTODO) to and from this neutral :class:`Task`. Only the
fields here are synced; anything system-specific is kept in ``raw`` and
ignored by the engine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Canonical priority scale: 0 = none, 1 = high, 2 = medium, 3 = low.
PRIORITY_NONE = 0
PRIORITY_HIGH = 1
PRIORITY_MEDIUM = 2
PRIORITY_LOW = 3


def utcnow() -> datetime:
    """Timezone-aware "now" in UTC."""
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to timezone-aware UTC (naive is assumed UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class Task:
    """A single to-do item in the neutral representation.

    ``title``, ``notes``, ``done``, ``due`` and ``priority`` are the synced
    payload. ``external_id`` and ``updated_at`` are metadata filled in by a
    connector when it lists tasks; they are never part of the content hash.
    """

    title: str
    notes: str = ""
    done: bool = False
    due: Optional[datetime] = None
    priority: int = PRIORITY_NONE

    # Metadata (not part of the content hash)
    external_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.notes = (self.notes or "").strip()
        self.due = as_utc(self.due)
        self.updated_at = as_utc(self.updated_at)

    def content_hash(self) -> str:
        """Stable hash of the *synced* payload only.

        Used to detect whether a task changed since the last sync without
        relying on (often unreliable) remote modification timestamps.
        """
        due = self.due.isoformat() if self.due else ""
        parts = [
            self.title,
            self.notes,
            "1" if self.done else "0",
            due,
            str(self.priority),
        ]
        blob = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def merge_payload_into(self, other: "Task") -> "Task":
        """Return a copy of ``other`` carrying this task's synced payload.

        Keeps ``other``'s identity (external_id) while adopting our content.
        """
        return Task(
            title=self.title,
            notes=self.notes,
            done=self.done,
            due=self.due,
            priority=self.priority,
            external_id=other.external_id,
            updated_at=self.updated_at,
            raw=other.raw,
        )
