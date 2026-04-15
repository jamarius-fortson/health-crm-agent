"""
Audit log models.

Every PHI access, every LLM call, every patient communication writes
an immutable audit entry. This is the compliance source of truth.

The audit database is write-only for the application — only compliance
officers can read from it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class AuditEventType(str, Enum):
    """Types of auditable events."""
    # PHI Access
    PHI_READ = "phi_read"
    PHI_WRITE = "phi_write"
    PHI_TRANSMIT = "phi_transmit"

    # LLM Calls
    LLM_CALL = "llm_call"
    LLM_RESPONSE = "llm_response"

    # Authentication
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    MFA_CHALLENGE = "mfa_challenge"
    SESSION_EXPIRED = "session_expired"

    # HITL
    HITL_ESCALATION = "hitl_escalation"
    HITL_APPROVAL = "hitl_approval"
    HITL_REJECTION = "hitl_rejection"

    # Safety
    CLINICAL_CONTENT_BLOCKED = "clinical_content_blocked"
    RED_FLAG_TRIGGERED = "red_flag_triggered"
    PHI_SCOPE_VIOLATION = "phi_scope_violation"
    BAA_ENDPOINT_VIOLATION = "baa_endpoint_violation"

    # System
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    BREACH_ALERT = "breach_alert"
    CONFIG_CHANGE = "config_change"

    # Agent Actions
    AGENT_ACTION = "agent_action"
    AGENT_ESCALATION = "agent_escalation"

    # Messaging
    MESSAGE_SENT = "message_sent"
    MESSAGE_BLOCKED = "message_blocked"
    MESSAGE_ESCALATED = "message_escalated"


class AuditEntry(BaseModel):
    """
    Immutable audit log entry.

    Every row represents one auditable action. The audit database enforces
    append-only constraints at the database level.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Who did it
    event_type: AuditEventType = Field(
        json_schema_extra={"phi_type": "operational"},
    )
    actor_id: str | None = Field(
        default=None,
        max_length=255,
        json_schema_extra={"phi_type": "operational"},
        description="User ID, agent name, or 'system'",
    )
    actor_role: str | None = Field(
        default=None,
        max_length=50,
        json_schema_extra={"phi_type": "operational"},
    )

    # Which patient (if applicable)
    patient_id: str | None = Field(
        default=None,
        json_schema_extra={"phi_type": "phi"},
        description="Patient UUID — PHI because it identifies a patient",
    )

    # What PHI was accessed (if applicable)
    phi_fields_accessed: list[str] = Field(
        default_factory=list,
        json_schema_extra={"phi_type": "operational"},
        description="List of PHI field names that were accessed",
    )

    # What happened
    action: str = Field(
        max_length=100,
        json_schema_extra={"phi_type": "operational"},
        description="Human-readable description of the action",
    )
    resource_type: str | None = Field(
        default=None,
        max_length=100,
        json_schema_extra={"phi_type": "operational"},
        description="Type of resource (Patient, Appointment, Message, etc.)",
    )
    resource_id: str | None = Field(
        default=None,
        max_length=255,
        json_schema_extra={"phi_type": "operational"},
        description="ID of the resource accessed",
    )

    # Additional context
    details: dict[str, Any] = Field(
        default_factory=dict,
        json_schema_extra={"phi_type": "operational"},
        description="Structured context — MUST NOT contain PHI values, only metadata",
    )

    # Request context
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        json_schema_extra={"phi_type": "operational"},
    )
    user_agent: str | None = Field(
        default=None,
        max_length=500,
        json_schema_extra={"phi_type": "operational"},
    )
    session_id: str | None = Field(
        default=None,
        max_length=255,
        json_schema_extra={"phi_type": "operational"},
    )

    @classmethod
    def create(
        cls,
        event_type: AuditEventType,
        action: str,
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
    ) -> "AuditEntry":
        """Factory method for creating audit entries."""
        return cls(
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
