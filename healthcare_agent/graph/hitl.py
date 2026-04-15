"""
Human-in-the-Loop (HITL) Management.

Manages the HITL queue for the supervisor graph. When an agent action
requires human approval, it creates a HITLItem and pauses that branch
of the graph until the item is resolved via the dashboard.

HITL is triggered for:
1. All clinical-content escalations (mandatory, no override)
2. Scheduling against blocked provider time
3. VIP/legal-hold patient appointments
4. Patients with 3+ recent cancellations
5. Prior authorization submissions (always)
6. Recall lists (always — clinician sign-off required)
7. Any red-flag trigger
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"  # Escalated to higher-level human
    EXPIRED = "expired"


class HITLPriority(str, Enum):
    CRITICAL = "critical"  # Red flag — immediate attention
    HIGH = "high"          # Prior auth, VIP patient
    NORMAL = "normal"      # Routine approval
    LOW = "low"            # Informational


class HITLItem:
    """A single item in the HITL queue."""

    def __init__(
        self,
        agent_name: str,
        action_type: str,
        description: str,
        patient_id: str | None = None,
        priority: HITLPriority = HITLPriority.NORMAL,
        context: dict[str, Any] | None = None,
        requires_action: bool = True,
        timeout_minutes: int = 60,
    ):
        self.id = str(uuid.uuid4())
        self.created_at = datetime.utcnow()
        self.agent_name = agent_name
        self.action_type = action_type
        self.patient_id = patient_id
        self.description = description
        self.priority = priority
        self.context = context or {}
        self.requires_action = requires_action
        self.timeout_minutes = timeout_minutes
        self.status = HITLStatus.PENDING
        self.resolved_at: datetime | None = None
        self.resolved_by: str | None = None
        self.resolution_notes: str | None = None

    @property
    def is_expired(self) -> bool:
        if self.resolved_at is not None:
            return False
        elapsed = (datetime.utcnow() - self.created_at).total_seconds() / 60
        return elapsed > self.timeout_minutes

    def resolve(
        self,
        status: HITLStatus,
        resolved_by: str,
        notes: str | None = None,
    ) -> None:
        """Mark this item as resolved."""
        if self.status != HITLStatus.PENDING:
            raise ValueError(f"HITL item {self.id} is already {self.status.value}")
        self.status = status
        self.resolved_at = datetime.utcnow()
        self.resolved_by = resolved_by
        self.resolution_notes = notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "patient_id": self.patient_id,
            "description": self.description,
            "priority": self.priority.value,
            "context": self.context,
            "requires_action": self.requires_action,
            "status": self.status.value,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_notes": self.resolution_notes,
            "is_expired": self.is_expired,
        }


class HITLQueue:
    """
    In-memory HITL queue for development/testing.

    In production, this is backed by the Postgres database with
    row-level security and real-time notifications.
    """

    def __init__(self) -> None:
        self._items: dict[str, HITLItem] = {}

    def add(self, item: HITLItem) -> str:
        """Add an item to the queue."""
        self._items[item.id] = item
        return item.id

    def get(self, item_id: str) -> HITLItem | None:
        """Get a specific HITL item."""
        return self._items.get(item_id)

    def pending(self) -> list[HITLItem]:
        """Get all pending items, sorted by priority."""
        priority_order = {
            HITLPriority.CRITICAL: 0,
            HITLPriority.HIGH: 1,
            HITLPriority.NORMAL: 2,
            HITLPriority.LOW: 3,
        }
        items = [
            item for item in self._items.values()
            if item.status == HITLStatus.PENDING
        ]
        return sorted(items, key=lambda i: priority_order[i.priority])

    def resolve(
        self,
        item_id: str,
        status: HITLStatus,
        resolved_by: str,
        notes: str | None = None,
    ) -> HITLItem:
        """Resolve a HITL item."""
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"HITL item {item_id} not found")
        item.resolve(status, resolved_by, notes)
        return item

    def pending_count(self) -> int:
        return len(self.pending())

    def has_critical(self) -> bool:
        return any(
            item.priority == HITLPriority.CRITICAL
            for item in self.pending()
        )

    def clear_resolved(self) -> None:
        """Remove resolved items older than 24 hours (cleanup)."""
        cutoff = datetime.utcnow()
        to_remove = [
            item_id for item_id, item in self._items.items()
            if item.resolved_at is not None
            and (cutoff - item.resolved_at).total_seconds() > 86400
        ]
        for item_id in to_remove:
            del self._items[item_id]


# Global HITL queue (swapped for production DB-backed queue)
_hitl_queue = HITLQueue()


def get_hitl_queue() -> HITLQueue:
    return _hitl_queue


def set_hitl_queue(queue: HITLQueue) -> None:
    global _hitl_queue
    _hitl_queue = queue
