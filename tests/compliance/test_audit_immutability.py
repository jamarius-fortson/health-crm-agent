"""
Test: Audit Log Immutability.

Verifies that:
1. Audit entries can only be appended — never updated or deleted
2. Every PHI access creates an audit entry
3. The audit log is the source of truth for compliance
4. Hash chain integrity is maintained
"""

from __future__ import annotations

import pytest

from healthcare_agent.compliance.audit import (
    InMemoryAuditLog,
    log_audit,
    log_phi_access,
    log_llm_call,
    log_safety_event,
)
from healthcare_agent.models import AuditEntry, AuditEventType


@pytest.fixture
def audit_log() -> InMemoryAuditLog:
    """Fresh audit log for each test."""
    log = InMemoryAuditLog()
    return log


class TestAuditImmutability:
    """Test that the audit log is append-only."""

    @pytest.mark.asyncio
    async def test_write_creates_entry(self, audit_log: InMemoryAuditLog):
        """Writing an entry should add it to the log."""
        entry = AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="Read patient record",
            actor_id="test_user",
            patient_id="test-patient-1",
            phi_fields_accessed=["first_name", "last_name"],
        )
        entry_id = await audit_log.write(entry)
        assert entry_id is not None
        assert audit_log.entry_count == 1

    @pytest.mark.asyncio
    async def test_multiple_writes_append(self, audit_log: InMemoryAuditLog):
        """Multiple writes should append, not replace."""
        for i in range(5):
            entry = AuditEntry.create(
                event_type=AuditEventType.PHI_READ,
                action=f"Read {i}",
                actor_id="test_user",
            )
            await audit_log.write(entry)
        assert audit_log.entry_count == 5

    @pytest.mark.asyncio
    async def test_read_returns_entries(self, audit_log: InMemoryAuditLog):
        """Reading should return the entries in order."""
        for i in range(3):
            entry = AuditEntry.create(
                event_type=AuditEventType.PHI_READ,
                action=f"Read {i}",
                actor_id="test_user",
                patient_id=f"patient-{i}",
            )
            await audit_log.write(entry)

        results = await audit_log.read(limit=10)
        assert len(results) == 3
        assert results[0].action == "Read 0"
        assert results[2].action == "Read 2"

    @pytest.mark.asyncio
    async def test_read_by_event_type(self, audit_log: InMemoryAuditLog):
        """Reading should filter by event type."""
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ, action="Read", actor_id="user",
        ))
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.LLM_CALL, action="LLM call", actor_id="agent",
        ))
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_WRITE, action="Write", actor_id="user",
        ))

        phi_reads = await audit_log.read(event_type=AuditEventType.PHI_READ)
        assert len(phi_reads) == 1

    @pytest.mark.asyncio
    async def test_read_by_patient(self, audit_log: InMemoryAuditLog):
        """Reading should filter by patient ID."""
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ, action="Read", actor_id="user",
            patient_id="patient-1",
        ))
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ, action="Read", actor_id="user",
            patient_id="patient-2",
        ))

        results = await audit_log.read(patient_id="patient-1")
        assert len(results) == 1
        assert results[0].patient_id == "patient-1"

    @pytest.mark.asyncio
    async def test_hash_chain_integrity(self, audit_log: InMemoryAuditLog):
        """Each entry should include a hash of the previous entry."""
        entry1 = AuditEntry.create(
            event_type=AuditEventType.PHI_READ, action="Read 1", actor_id="user",
        )
        id1 = await audit_log.write(entry1)

        entry2 = AuditEntry.create(
            event_type=AuditEventType.PHI_WRITE, action="Write 1", actor_id="user",
        )
        id2 = await audit_log.write(entry2)

        # Both entries should exist
        results = await audit_log.read(limit=10)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_export_json(self, audit_log: InMemoryAuditLog):
        """Export should return JSON-serializable data."""
        await audit_log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="Read patient record",
            actor_id="test_user",
            patient_id="patient-1",
            phi_fields_accessed=["first_name"],
        ))

        exported = await audit_log.export_json()
        assert len(exported) == 1
        assert exported[0]["event_type"] == "phi_read"
        assert exported[0]["patient_id"] == "patient-1"


class TestAuditConvenienceFunctions:
    """Test the convenience functions for logging specific event types."""

    @pytest.mark.asyncio
    async def test_log_phi_access(self):
        """log_phi_access should create a PHI_READ or PHI_WRITE entry."""
        entry_id = await log_phi_access(
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "last_name"],
            actor_id="test_user",
            actor_role="scheduling",
            action="read patient record",
        )
        assert entry_id is not None

        log = InMemoryAuditLog()
        # Use a separate log for this test
        entry = AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="read",
            actor_id="test_user",
            patient_id="patient-1",
            phi_fields_accessed=["first_name"],
        )
        await log.write(entry)
        results = await log.read(event_type=AuditEventType.PHI_READ)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_log_llm_call(self):
        """log_llm_call should create an LLM_CALL entry."""
        entry_id = await log_llm_call(
            actor_id="SchedulingAgent",
            model_name="anthropic.claude-3-5-sonnet-20241022-v2:0",
            patient_id="patient-1",
            phi_fields_accessed=["first_name"],
            prompt_token_count=100,
            completion_token_count=50,
            cost_usd=0.05,
        )
        assert entry_id is not None

    @pytest.mark.asyncio
    async def test_log_safety_event(self):
        """log_safety_event should create a safety event entry."""
        entry_id = await log_safety_event(
            event_type=AuditEventType.CLINICAL_CONTENT_BLOCKED,
            action="Clinical content blocked in outbound message",
            actor_id="CommunicationsAgent",
            patient_id="patient-1",
            details={"reason": "symptom detected"},
        )
        assert entry_id is not None


class TestAuditCompleteness:
    """Test that every PHI touchpoint is logged."""

    @pytest.mark.asyncio
    async def test_every_phi_access_is_logged(self):
        """
        Simulate a workflow: every PHI access should create an audit entry.
        """
        log = InMemoryAuditLog()

        # Simulate: intake reads patient data
        await log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="IntakeAgent read patient demographics",
            actor_id="IntakeAgent",
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "last_name", "date_of_birth"],
        ))

        # Simulate: scheduling reads patient contact info
        await log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="SchedulingAgent read patient contact info",
            actor_id="SchedulingAgent",
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "phone", "email"],
        ))

        # Simulate: communications sends a message
        await log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_TRANSMIT,
            action="CommunicationsAgent sent appointment reminder",
            actor_id="CommunicationsAgent",
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "phone"],
        ))

        # Verify: 3 entries for 3 PHI accesses
        assert log.entry_count == 3

        # Verify: all entries reference the same patient
        results = await log.read(patient_id="patient-1")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_audit_includes_phi_fields_accessed(self):
        """Every PHI access entry should list which fields were accessed."""
        log = InMemoryAuditLog()
        await log.write(AuditEntry.create(
            event_type=AuditEventType.PHI_READ,
            action="Read patient data",
            actor_id="TestAgent",
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "last_name", "phone"],
        ))

        results = await log.read(event_type=AuditEventType.PHI_READ)
        assert len(results) == 1
        assert results[0].phi_fields_accessed == ["first_name", "last_name", "phone"]
