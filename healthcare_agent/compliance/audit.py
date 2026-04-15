"""
Immutable Audit Log.

Every PHI access, every LLM call, every patient communication writes one row
to a write-only audit database.

Properties:
- Append-only: enforced at the database level with triggers
- Tamper-evident: each entry includes a hash of the previous entry (chain)
- Write-only for application: only compliance officers can read
- Exportable: CSV/JSON export for compliance audits

In production, this writes to Postgres with RLS + append-only triggers + WORM storage.
For development/testing, an in-memory implementation is available.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Protocol

from healthcare_agent.models import AuditEntry, AuditEventType


class AuditLogBackend(ABC):
    """Abstract backend for the audit log."""

    @abstractmethod
    async def write(self, entry: AuditEntry) -> str:
        """Write an audit entry. Returns the entry ID. Always appends."""

    @abstractmethod
    async def read(
        self,
        *,
        event_type: AuditEventType | None = None,
        patient_id: str | None = None,
        actor_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Read audit entries (compliance officer only)."""

    @abstractmethod
    async def export_json(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Export audit log as JSON for compliance audit."""


class InMemoryAuditLog(AuditLogBackend):
    """
    In-memory audit log for development and testing.

    NOT for production use — does not enforce immutability.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._previous_hash: str = "0" * 64  # Genesis hash

    async def write(self, entry: AuditEntry) -> str:
        # Create hash chain
        entry_data = entry.model_dump_json()
        chain_hash = hashlib.sha256(
            f"{self._previous_hash}{entry_data}".encode()
        ).hexdigest()
        self._previous_hash = chain_hash

        self._entries.append(entry)
        return entry.id

    async def read(
        self,
        *,
        event_type: AuditEventType | None = None,
        patient_id: str | None = None,
        actor_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results = self._entries

        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if patient_id is not None:
            results = [e for e in results if e.patient_id == patient_id]
        if actor_id is not None:
            results = [e for e in results if e.actor_id == actor_id]
        if since is not None:
            results = [e for e in results if e.timestamp >= since]

        return results[-limit:]

    async def export_json(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        results = self._entries
        if since is not None:
            results = [e for e in results if e.timestamp >= since]
        if until is not None:
            results = [e for e in results if e.timestamp <= until]
        return [e.model_dump(mode="json") for e in results]

    def clear(self) -> None:
        """Clear entries (testing only)."""
        self._entries.clear()
        self._previous_hash = "0" * 64

    @property
    def entry_count(self) -> int:
        return len(self._entries)


# Global audit log instance (swapped for production DB backend)
_audit_log: AuditLogBackend = InMemoryAuditLog()


def get_audit_log() -> AuditLogBackend:
    """Get the current audit log backend."""
    return _audit_log


def set_audit_log(backend: AuditLogBackend) -> None:
    """Set the audit log backend (called during app startup)."""
    global _audit_log
    _audit_log = backend


async def log_audit(
    event_type: AuditEventType,
    action: str,
    *,
    actor_id: str | None = None,
    actor_role: str | None = None,
    patient_id: str | None = None,
    phi_fields_accessed: list[str] | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Write an audit entry to the audit log.

    This is the primary interface for recording audit events.
    Every PHI touchpoint MUST call this function.
    """
    entry = AuditEntry.create(
        event_type=event_type,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        patient_id=patient_id,
        phi_fields_accessed=phi_fields_accessed or [],
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id,
    )

    entry_id = await get_audit_log().write(entry)
    return entry_id


async def log_phi_access(
    patient_id: str,
    phi_fields_accessed: list[str],
    *,
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> str:
    """
    Convenience function for logging PHI access.

    This automatically sets the event type to PHI_READ or PHI_WRITE
    based on the action.
    """
    event_type = AuditEventType.PHI_WRITE if "write" in action.lower() else AuditEventType.PHI_READ

    return await log_audit(
        event_type=event_type,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        patient_id=patient_id,
        phi_fields_accessed=phi_fields_accessed,
        resource_type=resource_type,
        resource_id=resource_id,
    )


async def log_llm_call(
    *,
    actor_id: str,
    model_name: str,
    patient_id: str | None = None,
    phi_fields_accessed: list[str] | None = None,
    prompt_token_count: int | None = None,
    completion_token_count: int | None = None,
    cost_usd: float | None = None,
) -> str:
    """Log an LLM call for compliance tracking."""
    return await log_audit(
        event_type=AuditEventType.LLM_CALL,
        action=f"LLM call to {model_name}",
        actor_id=actor_id,
        patient_id=patient_id,
        phi_fields_accessed=phi_fields_accessed or [],
        details={
            "model_name": model_name,
            "prompt_token_count": prompt_token_count,
            "completion_token_count": completion_token_count,
            "cost_usd": cost_usd,
        },
    )


async def log_safety_event(
    *,
    event_type: AuditEventType,
    action: str,
    actor_id: str | None = None,
    patient_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    """Log a safety event (red flag, clinical content blocked, etc.)."""
    return await log_audit(
        event_type=event_type,
        action=action,
        actor_id=actor_id,
        patient_id=patient_id,
        details=details or {},
    )
