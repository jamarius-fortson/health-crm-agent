"""
End-to-End Test: Full Workflow with Synthetic Synthea Data.

This test simulates the hero demo workflow:
1. New patient (synthetic Synthea) submits an intake form
2. Agent verifies insurance
3. Schedules appointment
4. Sends confirmation
5. Patient texts back to reschedule
6. Agent reschedules
7. Patient texts "I have chest pain"
8. Agent immediately routes to HITL with red-flag escalation

ALL data is synthetic — no real PHI is used.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from healthcare_agent.agents.scheduling import SchedulingAgent
from healthcare_agent.safety.red_flag_rules import check_red_flags, RedFlagSeverity
from healthcare_agent.safety.content_classifier import classify_message, ClassificationVerdict
from healthcare_agent.compliance.audit import InMemoryAuditLog, log_audit, set_audit_log
from healthcare_agent.compliance.minimum_necessary import enforce_scope, SCHEDULING_SCOPE
from healthcare_agent.models.audit import AuditEventType
from healthcare_agent.graph.hitl import HITLQueue, HITLItem, HITLPriority


# ============================================================================
# Synthetic Synthea-like Test Patient
# ============================================================================

SYNTHETIC_PATIENT = {
    "id": "synthea-patient-001",
    "first_name": "Maria",
    "last_name": "Garcia",
    "date_of_birth": "1985-03-15",
    "phone": "+15551234567",
    "email": "maria.garcia@synthetic.example.com",
    "street_address": "123 Synthetic Lane",
    "city": "Springfield",
    "state": "NY",
    "zip_code": "12345",
    "language": "en",
    "status": "active",
}

SYNTHETIC_CLINIC_CONFIG = {
    "providers": {
        "dr-smith": {
            "name": "Dr. Smith",
            "specialty": "Primary Care",
            "blocked_times": [],
        },
    },
    "appointment_types": {
        "new_patient": {
            "display_name": "New Patient Visit",
            "duration_minutes": 30,
        },
        "follow_up": {
            "display_name": "Follow-Up Visit",
            "duration_minutes": 15,
        },
    },
    "scheduling_rules": {
        "max_cancellations_before_hitl": 3,
    },
}


class TestEndToEndWorkflow:
    """End-to-end workflow test."""

    @pytest.fixture
    def audit_log(self) -> InMemoryAuditLog:
        """Fresh audit log."""
        log = InMemoryAuditLog()
        set_audit_log(log)
        return log

    @pytest.fixture
    def hitl_queue(self) -> HITLQueue:
        """Fresh HITL queue."""
        return HITLQueue()

    @pytest.mark.asyncio
    async def test_full_workflow(self, audit_log: InMemoryAuditLog, hitl_queue: HITLQueue):
        """
        Test the complete workflow:
        intake → schedule → confirm → reschedule → red-flag escalation
        """

        # --- Step 1: Patient submits intake form ---
        # Simulate intake processing
        await log_audit(
            event_type=AuditEventType.PHI_READ,
            action="IntakeAgent processed new patient intake form",
            actor_id="IntakeAgent",
            patient_id=SYNTHETIC_PATIENT["id"],
            phi_fields_accessed=["first_name", "last_name", "date_of_birth", "phone", "email"],
            resource_type="IntakeSummary",
            details={"synthetic_data": True},
        )

        # Verify audit
        assert audit_log.entry_count == 1

        # --- Step 2: Schedule appointment ---
        scheduling_agent = SchedulingAgent()
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=10)

        state = {
            "patient_id": SYNTHETIC_PATIENT["id"],
            "patient": SCHEDULING_SCOPE.strip_to_scope(SYNTHETIC_PATIENT),
            "current_task": "schedule_appointment",
            "clinic_config": SYNTHETIC_CLINIC_CONFIG,
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "new_patient",
                "requested_time": tomorrow.isoformat(),
            },
            "hitl_queue": [],
            "audit_entry_ids": [],
        }

        result = await scheduling_agent.run(state)
        assert result["agent_results"]["scheduling"]["status"] == "scheduled"
        appointment = result["agent_results"]["scheduling"]["appointment"]

        # Log the scheduling
        await log_audit(
            event_type=AuditEventType.PHI_WRITE,
            action="SchedulingAgent booked appointment",
            actor_id="SchedulingAgent",
            patient_id=SYNTHETIC_PATIENT["id"],
            phi_fields_accessed=["first_name", "phone"],
            resource_type="Appointment",
            resource_id=appointment["id"],
        )

        assert audit_log.entry_count == 2

        # --- Step 3: Send confirmation ---
        await log_audit(
            event_type=AuditEventType.PHI_TRANSMIT,
            action="CommunicationsAgent sent appointment confirmation",
            actor_id="CommunicationsAgent",
            patient_id=SYNTHETIC_PATIENT["id"],
            phi_fields_accessed=["first_name", "phone"],
            resource_type="Message",
            details={"synthetic_data": True},
        )

        assert audit_log.entry_count == 3

        # --- Step 4: Patient texts to reschedule ---
        next_week = tomorrow + timedelta(days=7)
        state["current_task"] = "reschedule_appointment"
        state["task_context"] = {
            "appointment_id": appointment["id"],
            "appointment": appointment,
            "new_time": next_week.isoformat(),
        }

        result = await scheduling_agent.run(state)
        assert result["agent_results"]["scheduling"]["status"] == "rescheduled"

        await log_audit(
            event_type=AuditEventType.PHI_WRITE,
            action="SchedulingAgent rescheduled appointment",
            actor_id="SchedulingAgent",
            patient_id=SYNTHETIC_PATIENT["id"],
            phi_fields_accessed=["first_name", "phone"],
            resource_type="Appointment",
            resource_id=appointment["id"],
        )

        assert audit_log.entry_count == 4

        # --- Step 5: Patient texts "I have chest pain" ---
        chest_pain_message = "I have chest pain and I'm worried"

        # Red-flag check
        trigger = check_red_flags(chest_pain_message)
        assert trigger.triggered, "Chest pain MUST trigger red flag"
        assert trigger.rule is not None
        assert trigger.rule.severity == RedFlagSeverity.CRITICAL
        assert trigger.rule.category.name == "CARDIAC"

        # Content classification check
        classification = classify_message(chest_pain_message)
        assert classification.verdict == ClassificationVerdict.BLOCKED
        assert classification.requires_hitl

        # Create HITL item
        hitl_item = HITLItem(
            agent_name="CommunicationsAgent",
            action_type="red_flag_escalation",
            description=f"Red flag triggered: {trigger.rule.name}",
            patient_id=SYNTHETIC_PATIENT["id"],
            priority=HITLPriority.CRITICAL,
            context={
                "message": chest_pain_message,
                "red_flag_rule": trigger.rule.rule_id,
                "auto_response": trigger.rule.auto_response,
            },
        )
        hitl_queue.add(hitl_item)

        # Log the escalation
        await log_audit(
            event_type=AuditEventType.RED_FLAG_TRIGGERED,
            action=f"Red flag: {trigger.rule.name}",
            actor_id="CommunicationsAgent",
            patient_id=SYNTHETIC_PATIENT["id"],
            details={
                "rule_id": trigger.rule.rule_id,
                "category": trigger.rule.category.value,
                "severity": trigger.rule.severity.value,
                "matched_text": trigger.matched_text,
                "synthetic_data": True,
            },
        )

        # Verify HITL queue has the critical item
        assert hitl_queue.has_critical()
        assert hitl_queue.pending_count() == 1

        # Verify audit log captures the escalation
        assert audit_log.entry_count == 5

        # --- Step 6: Verify auto-response is correct ---
        auto_response = trigger.rule.auto_response
        assert "911" in auto_response or "emergency" in auto_response.lower()

        # --- Final verification ---
        # All audit entries reference the synthetic patient
        entries = await audit_log.read(patient_id=SYNTHETIC_PATIENT["id"])
        assert len(entries) == 5

        # The last entry is the red-flag escalation
        assert entries[-1].event_type == AuditEventType.RED_FLAG_TRIGGERED

    @pytest.mark.asyncio
    async def test_audit_log_captures_every_phi_access(self, audit_log: InMemoryAuditLog):
        """Every PHI access in the workflow should be logged."""
        # Simulate the workflow
        await log_audit(
            event_type=AuditEventType.PHI_READ,
            action="Read patient demographics",
            actor_id="IntakeAgent",
            patient_id="patient-1",
            phi_fields_accessed=["first_name", "last_name", "date_of_birth"],
        )
        await log_audit(
            event_type=AuditEventType.PHI_READ,
            action="Read patient contact info",
            actor_id="SchedulingAgent",
            patient_id="patient-1",
            phi_fields_accessed=["phone", "email"],
        )
        await log_audit(
            event_type=AuditEventType.PHI_TRANSMIT,
            action="Sent reminder",
            actor_id="CommunicationsAgent",
            patient_id="patient-1",
            phi_fields_accessed=["phone"],
        )

        entries = await audit_log.read(patient_id="patient-1")
        assert len(entries) == 3

        # Verify each entry has phi_fields_accessed
        for entry in entries:
            assert len(entry.phi_fields_accessed) > 0

    @pytest.mark.asyncio
    async def test_scheduling_scope_enforcement_in_workflow(self):
        """Scheduling scope should strip clinical fields during workflow."""
        full_patient = {
            "first_name": "Maria",
            "last_name": "Garcia",
            "phone": "+15551234567",
            "email": "maria@synthetic.example.com",
            "date_of_birth": "1985-03-15",
            "chief_complaint": "Annual physical",  # Clinical — should be stripped
            "current_medications": ["Metformin"],  # Clinical — should be stripped
            "known_allergies": ["Penicillin"],  # Clinical — should be stripped
        }

        scoped = SCHEDULING_SCOPE.strip_to_scope(full_patient)
        assert scoped["first_name"] == "Maria"
        assert scoped["phone"] == "+15551234567"
        assert "chief_complaint" not in scoped
        assert "current_medications" not in scoped
        assert "known_allergies" not in scoped
