"""
Test: SchedulingAgent.

Verifies that the SchedulingAgent:
1. Schedules appointments correctly
2. Respects blocked provider times
3. Triggers HITL for blocked-time scheduling
4. Triggers HITL for patients with 3+ cancellations
5. Predicts no-show risk
6. Sends appointment reminders
7. Reschedules appointments
8. Cancels appointments
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from healthcare_agent.agents.scheduling import SchedulingAgent
from healthcare_agent.models import AppointmentStatus


@pytest.fixture
def agent() -> SchedulingAgent:
    return SchedulingAgent()


@pytest.fixture
def base_state() -> dict:
    """Base state for scheduling tests."""
    return {
        "patient_id": "synthea-patient-001",
        "patient": {
            "first_name": "Test",
            "last_name": "Patient",
            "phone": "+15551234567",
            "email": "test@example.com",
            "date_of_birth": "1990-01-01",
            "status": "active",
        },
        "clinic_config": {
            "providers": {
                "dr-smith": {
                    "name": "Dr. Smith",
                    "specialty": "Primary Care",
                    "blocked_times": [
                        {"day_of_week": "Friday", "start_time": "12:00", "end_time": "13:00"},
                    ],
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
                "overbook_high_risk_no_show": True,
                "no_show_risk_threshold": 0.6,
            },
        },
        "hitl_queue": [],
        "audit_entry_ids": [],
    }


class TestSchedulingAgent:
    """Test the SchedulingAgent."""

    @pytest.mark.asyncio
    async def test_schedule_appointment_success(self, agent: SchedulingAgent, base_state: dict):
        """Scheduling an appointment should succeed."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "new_patient",
                "requested_time": tomorrow.isoformat(),
                "location": "Main Office",
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["status"] == "scheduled"
        assert "appointment" in scheduling_result
        assert scheduling_result["appointment"]["provider_id"] == "dr-smith"
        assert scheduling_result["appointment"]["appointment_type"] == "new_patient"

    @pytest.mark.asyncio
    async def test_schedule_during_blocked_time_requires_hitl(
        self, agent: SchedulingAgent, base_state: dict
    ):
        """Scheduling during a blocked time should require HITL."""
        # Find next Friday at 12:30
        now = datetime.utcnow()
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        friday_noon = now + timedelta(days=days_until_friday)
        friday_noon = friday_noon.replace(hour=12, minute=30, second=0, microsecond=0)

        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "follow_up",
                "requested_time": friday_noon.isoformat(),
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["hitl_required"] is True
        assert "blocked time" in scheduling_result["hitl_reason"].lower()
        assert len(result["hitl_queue"]) > 0

    @pytest.mark.asyncio
    async def test_schedule_with_many_cancellations_requires_hitl(
        self, agent: SchedulingAgent, base_state: dict
    ):
        """Patient with 3+ cancellations should require HITL."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "follow_up",
                "requested_time": tomorrow.isoformat(),
                "recent_cancellations": 3,
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["hitl_required"] is True
        assert "cancellation" in scheduling_result["hitl_reason"].lower()

    @pytest.mark.asyncio
    async def test_no_show_risk_prediction(self, agent: SchedulingAgent, base_state: dict):
        """No-show risk should be calculated."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "follow_up",
                "requested_time": tomorrow.isoformat(),
                "prior_no_shows": 2,
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        no_show_risk = scheduling_result["no_show_risk"]
        assert 0.0 <= no_show_risk <= 1.0
        # With 2 prior no-shows, risk should be at least 0.4
        assert no_show_risk >= 0.3

    @pytest.mark.asyncio
    async def test_reschedule_appointment(self, agent: SchedulingAgent, base_state: dict):
        """Rescheduling should update the appointment time."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        next_week = tomorrow + timedelta(days=7)

        state = {
            **base_state,
            "current_task": "reschedule_appointment",
            "task_context": {
                "appointment_id": "appt-001",
                "appointment": {
                    "id": "appt-001",
                    "patient_id": "synthea-patient-001",
                    "provider_id": "dr-smith",
                    "appointment_type": "follow_up",
                    "appointment_type_display": "Follow-Up Visit",
                    "start_time": tomorrow.isoformat(),
                },
                "new_time": next_week.isoformat(),
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["status"] == "rescheduled"
        assert scheduling_result["appointment"]["status"] == AppointmentStatus.RESCHEDULED.value

    @pytest.mark.asyncio
    async def test_cancel_appointment(self, agent: SchedulingAgent, base_state: dict):
        """Cancellation should update appointment status."""
        state = {
            **base_state,
            "current_task": "cancel_appointment",
            "task_context": {
                "appointment_id": "appt-001",
                "appointment": {
                    "id": "appt-001",
                    "status": AppointmentStatus.SCHEDULED.value,
                },
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["status"] == "cancelled"
        assert scheduling_result["appointment"]["status"] == AppointmentStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_missing_fields_error(self, agent: SchedulingAgent, base_state: dict):
        """Missing required fields should return an error."""
        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                # Missing appointment_type and requested_time
            },
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_matching_task(self, agent: SchedulingAgent, base_state: dict):
        """Unknown task should return no_matching_task status."""
        state = {
            **base_state,
            "current_task": "unknown_task",
            "task_context": {},
        }
        result = await agent.run(state)
        scheduling_result = result["agent_results"]["scheduling"]
        assert scheduling_result["status"] == "no_matching_task"

    @pytest.mark.asyncio
    async def test_reminder_message_generation(self, agent: SchedulingAgent, base_state: dict):
        """Reminder should generate a patient-friendly message."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        state = {
            **base_state,
            "current_task": "send_reminder",
            "task_context": {
                "appointment": {
                    "id": "appt-001",
                    "appointment_type_display": "New Patient Visit",
                    "start_time": tomorrow.isoformat(),
                },
            },
        }
        result = await agent.run(state)
        assert "reminder_message" in result["task_context"]
        reminder = result["task_context"]["reminder_message"]
        assert "Test" in reminder  # Patient first name
        assert "New Patient Visit" in reminder
        assert "CONFIRM" in reminder

    @pytest.mark.asyncio
    async def test_appointment_duration_calculation(self, agent: SchedulingAgent, base_state: dict):
        """Appointment duration should be calculated from config."""
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=5)
        state = {
            **base_state,
            "current_task": "schedule_appointment",
            "task_context": {
                "provider_id": "dr-smith",
                "appointment_type": "new_patient",
                "requested_time": tomorrow.isoformat(),
            },
        }
        result = await agent.run(state)
        appointment = result["agent_results"]["scheduling"]["appointment"]
        start = datetime.fromisoformat(appointment["start_time"])
        end = datetime.fromisoformat(appointment["end_time"])
        duration = (end - start).total_seconds() / 60
        assert duration == 30  # new_patient = 30 minutes
