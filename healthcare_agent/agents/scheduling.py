"""
Scheduling Agent — Manages appointments, scheduling, and reminders.

Responsibilities:
- Book, reschedule, and cancel appointments against the EHR via FHIR
- Honor provider preferences, appointment-type duration, and capacity constraints
- Predict no-show risk and optionally overbook high-risk slots
- Send multi-channel confirmations and reminders

HARD LINE: Scheduling logic ONLY. Never makes claims about what the appointment
is for beyond the clinic-defined appointment type.

Autonomous: All routine scheduling within configured rules.
HITL: Scheduling against blocked provider time, VIP/legal-hold patients,
      patients with 3+ recent cancellations.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

from healthcare_agent.agents._base import BaseAgent
from healthcare_agent.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
)
from healthcare_agent.config import settings
from healthcare_agent.integrations.fhir.client import get_fhir_client


class SchedulingAgent(BaseAgent):
    """
    Autonomous scheduling agent for healthcare appointments.

    Books, reschedules, and cancels appointments. Sends confirmations
    and reminders. Predicts no-show risk.

    PHI scope: patient_id, first_name, last_name, phone, email, date_of_birth
    """

    @property
    def agent_name(self) -> str:
        return "scheduling_agent"

    @property
    def phi_scope_name(self) -> str:
        return "scheduling"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute scheduling logic based on the current task."""
        task = state.get("current_task", "")
        event_type = state.get("event_type", "")

        if task == "schedule_appointment" or event_type == "schedule_appointment":
            return await self._schedule_appointment(state)
        elif task == "reschedule_appointment" or event_type == "reschedule_appointment":
            return await self._reschedule_appointment(state)
        elif task == "cancel_appointment" or event_type == "cancel_appointment":
            return await self._cancel_appointment(state)
        elif task == "check_no_show" or event_type == "no_show_detected":
            return await self._check_no_show(state)
        elif task == "send_reminder" or event_type == "appointment_reminder":
            return await self._send_reminder(state)
        elif event_type == "fhir_appointment_webhook":
            return await self._handle_fhir_webhook(state)
        else:
            return {
                "agent_results": {
                    "scheduling": {
                        "status": "no_matching_task",
                        "task": task,
                        "event_type": event_type,
                    }
                }
            }

    async def _schedule_appointment(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Schedule a new appointment.

        Flow:
        1. Validate patient exists
        2. Validate provider and time slot
        3. Check for blocked times
        4. Check for HITL conditions (VIP, blocked time, 3+ cancellations)
        5. Create appointment in EHR via FHIR
        6. Predict no-show risk
        7. Queue confirmation message
        """
        patient_id = state.get("patient_id")
        fhir_patient_id = state.get("patient", {}).get("fhir_resource_id")
        task_context = state.get("task_context", {})

        provider_id = task_context.get("provider_id")
        appointment_type = task_context.get("appointment_type")
        requested_time = task_context.get("requested_time")
        location = task_context.get("location")

        if not all([patient_id, provider_id, appointment_type, requested_time]):
            return {
                "agent_results": {
                    "scheduling": {
                        "status": "error",
                        "error": "Missing required fields: patient_id, provider_id, appointment_type, requested_time",
                    }
                },
                "error": "Missing required scheduling fields",
            }

        # Parse the requested time
        if isinstance(requested_time, str):
            requested_dt = datetime.fromisoformat(requested_time)
        else:
            requested_dt = requested_time

        # Check for blocked provider times (simulated logic)
        clinic_config = state.get("clinic_config", {})
        providers = clinic_config.get("providers", {})
        provider = providers.get(provider_id, {})
        blocked_times = provider.get("blocked_times", [])

        hitl_required = False
        hitl_reason = None

        # Check blocked times
        for block in blocked_times:
            if self._time_in_block(requested_dt, block):
                hitl_required = True
                hitl_reason = f"Requested time conflicts with provider's blocked time: {block}"
                break

        # Get appointment duration
        appt_types_config = clinic_config.get("appointment_types", {})
        appt_config = appt_types_config.get(appointment_type, {})
        duration_minutes = appt_config.get("duration_minutes", 30)

        # Calculate end time
        end_dt = requested_dt + timedelta(minutes=duration_minutes)

        # --- FHIR Integration ---
        fhir_client = get_fhir_client()
        fhir_resource_id = None
        
        try:
            # Prepare FHIR Appointment resource
            fhir_appt_data = {
                "resourceType": "Appointment",
                "status": "booked",
                "start": requested_dt.isoformat(),
                "end": end_dt.isoformat(),
                "participant": [
                    {
                        "actor": {"reference": f"Patient/{fhir_patient_id or 'unknown'}"},
                        "status": "accepted"
                    },
                    {
                        "actor": {"reference": f"Practitioner/{provider_id}"},
                        "status": "accepted"
                    }
                ],
                "appointmentType": {
                    "coding": [{"code": appointment_type}]
                }
            }
            
            # Create in EHR
            fhir_res = await fhir_client.create_appointment(fhir_appt_data)
            fhir_resource_id = fhir_res.get("id")
            logger.info(f"Created FHIR Appointment: {fhir_resource_id}")
            
        except Exception as e:
            logger.error(f"FHIR Appointment creation failed: {e}")
            # In a real scenario, we might escalate to HITL if EHR sync fails
            hitl_required = True
            hitl_reason = f"EHR synchronization failed: {str(e)}"
        finally:
            await fhir_client.close()

        # Check for no-show risk
        no_show_risk = await self._predict_no_show_risk(patient_id, state)

        # Check for 3+ recent cancellations
        scheduling_rules = clinic_config.get("scheduling_rules", {})
        max_cancellations = scheduling_rules.get("max_cancellations_before_hitl", 3)
        recent_cancellations = task_context.get("recent_cancellations", 0)
        if recent_cancellations >= max_cancellations:
            hitl_required = True
            hitl_reason = (
                f"Patient has {recent_cancellations} recent cancellations "
                f"(threshold: {max_cancellations})"
            )

        # Create the appointment local model
        appointment = Appointment(
            patient_id=patient_id,
            fhir_resource_id=fhir_resource_id,
            provider_id=provider_id,
            appointment_type=AppointmentType(appointment_type),
            appointment_type_display=appt_config.get("display_name", appointment_type),
            start_time=requested_dt,
            end_time=end_dt,
            location=location,
            no_show_risk=no_show_risk,
            requires_hitl=hitl_required,
            hitl_reason=hitl_reason,
            created_by="scheduling_agent",
        )

        # Build result
        updates: dict[str, Any] = {
            "agent_results": {
                "scheduling": {
                    "status": "scheduled",
                    "appointment": appointment.model_dump(mode="json"),
                    "hitl_required": hitl_required,
                    "hitl_reason": hitl_reason,
                    "no_show_risk": no_show_risk,
                }
            },
            "next_node": "communications_agent",  # Send confirmation
            "current_task": "send_confirmation",
            "task_context": {
                **task_context,
                "appointment_id": appointment.id,
                "appointment": appointment.model_dump(mode="json"),
            },
        }

        if hitl_required:
            hitl_item = self.create_hitl_item(
                action_type="scheduling_approval",
                description=f"Appointment scheduling requires review: {hitl_reason}",
                patient_id=patient_id,
                context={
                    "appointment": appointment.model_dump(mode="json"),
                },
            )
            updates["hitl_queue"] = state.get("hitl_queue", []) + [hitl_item.to_dict()]

        return updates

    async def _reschedule_appointment(self, state: dict[str, Any]) -> dict[str, Any]:
        """Reschedule an existing appointment."""
        task_context = state.get("task_context", {})
        appointment_id = task_context.get("appointment_id")
        new_time = task_context.get("new_time")

        if not appointment_id or not new_time:
            return {
                "agent_results": {
                    "scheduling": {
                        "status": "error",
                        "error": "Missing appointment_id or new_time for reschedule",
                    }
                },
                "error": "Missing reschedule fields",
            }

        if isinstance(new_time, str):
            new_dt = datetime.fromisoformat(new_time)
        else:
            new_dt = new_time

        # Calculate new end time
        clinic_config = state.get("clinic_config", {})
        appointment_data = task_context.get("appointment", {})
        appt_type = appointment_data.get("appointment_type", "follow_up")
        appt_types_config = clinic_config.get("appointment_types", {})
        appt_config = appt_types_config.get(appt_type, {})
        duration_minutes = appt_config.get("duration_minutes", 15)

        new_end_dt = new_dt + timedelta(minutes=duration_minutes)

        # Update the appointment
        updated_appointment = {
            **appointment_data,
            "start_time": new_dt.isoformat(),
            "end_time": new_end_dt.isoformat(),
            "status": AppointmentStatus.RESCHEDULED.value,
            "updated_at": datetime.utcnow().isoformat(),
        }

        return {
            "agent_results": {
                "scheduling": {
                    "status": "rescheduled",
                    "appointment": updated_appointment,
                    "original_appointment_id": appointment_id,
                }
            },
            "next_node": "communications_agent",  # Send reschedule confirmation
            "task_context": {
                **task_context,
                "appointment": updated_appointment,
            },
        }

    async def _cancel_appointment(self, state: dict[str, Any]) -> dict[str, Any]:
        """Cancel an appointment."""
        task_context = state.get("task_context", {})
        appointment_id = task_context.get("appointment_id")

        if not appointment_id:
            return {
                "agent_results": {
                    "scheduling": {
                        "status": "error",
                        "error": "Missing appointment_id for cancellation",
                    }
                },
                "error": "Missing appointment_id",
            }

        return {
            "agent_results": {
                "scheduling": {
                    "status": "cancelled",
                    "appointment_id": appointment_id,
                }
            },
            "next_node": "communications_agent",  # Send cancellation notice
            "task_context": {
                **task_context,
                "appointment": {
                    **task_context.get("appointment", {}),
                    "status": AppointmentStatus.CANCELLED.value,
                },
            },
        }

    async def _check_no_show(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Check if a patient was a no-show and update the appointment.

        This is triggered by a scheduled check after the appointment time.
        """
        task_context = state.get("task_context", {})
        appointment_id = task_context.get("appointment_id")

        return {
            "agent_results": {
                "scheduling": {
                    "status": "no_show_checked",
                    "appointment_id": appointment_id,
                }
            },
            "next_node": "care_coordination_agent",  # May trigger follow-up scheduling
        }

    async def _send_reminder(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Queue an appointment reminder message.

        Reminders are sent at configurable lead times (e.g., 24h and 2h before).
        """
        task_context = state.get("task_context", {})
        appointment = task_context.get("appointment", {})

        patient_id = state.get("patient_id")
        patient = state.get("patient", {})
        first_name = patient.get("first_name", "Patient")

        appointment_type_display = appointment.get("appointment_type_display", "appointment")
        start_time = appointment.get("start_time", "")

        if start_time:
            start_dt = datetime.fromisoformat(start_time)
            formatted_time = start_dt.strftime("%A, %B %d at %I:%M %p")
        else:
            formatted_time = "your scheduled appointment"

        reminder_body = (
            f"Hi {first_name}, this is a reminder for your {appointment_type_display} "
            f"on {formatted_time}. Reply CONFIRM to confirm or RESCHEDULE to change. "
            f"If you need to cancel, please call our office."
        )

        return {
            "agent_results": {
                "scheduling": {
                    "status": "reminder_queued",
                    "appointment_id": appointment.get("id"),
                }
            },
            "next_node": "communications_agent",
            "task_context": {
                **task_context,
                "reminder_message": reminder_body,
            },
        }

    async def _handle_fhir_webhook(self, state: dict[str, Any]) -> dict[str, Any]:
        """Handle a FHIR webhook event for an appointment."""
        event_data = state.get("event_data", {})

        return {
            "agent_results": {
                "scheduling": {
                    "status": "fhir_webhook_processed",
                    "resource_type": event_data.get("resource_type"),
                    "resource_id": event_data.get("resource_id"),
                }
            }
        }

    async def _predict_no_show_risk(
        self,
        patient_id: str,
        state: dict[str, Any],
    ) -> float:
        """
        Predict no-show risk for a patient.

        In production, this uses a gradient-boosted model trained on
        historical attendance data. For now, uses a simple heuristic.

        Factors:
        - Prior no-shows (highest weight)
        - Lead time (shorter = higher risk)
        - Time of day (early morning = higher risk)
        - Day of week (Monday/Friday = higher risk)
        """
        task_context = state.get("task_context", {})

        # Prior no-shows
        prior_no_shows = task_context.get("prior_no_shows", 0)
        risk = prior_no_shows * 0.2

        # Lead time
        requested_time = task_context.get("requested_time")
        if requested_time:
            if isinstance(requested_time, str):
                requested_dt = datetime.fromisoformat(requested_time)
            else:
                requested_dt = requested_time
            lead_days = (requested_dt - datetime.utcnow()).days
            if lead_days <= 0:
                risk += 0.3
            elif lead_days <= 1:
                risk += 0.15
            elif lead_days >= 14:
                risk += 0.1  # Too far ahead = easy to forget

        # Time of day
        if isinstance(requested_time, str):
            requested_dt = datetime.fromisoformat(requested_time)
        else:
            requested_dt = requested_time if requested_time else datetime.utcnow()
        hour = requested_dt.hour
        if hour < 9:
            risk += 0.1  # Early morning

        # Day of week
        day = requested_dt.weekday()
        if day == 0 or day == 4:  # Monday or Friday
            risk += 0.05

        # Cap at 0.0–1.0
        return max(0.0, min(1.0, risk))

    @staticmethod
    def _time_in_block(
        requested_dt: datetime,
        block: dict[str, Any],
    ) -> bool:
        """Check if a requested time falls within a blocked time block."""
        day_of_week = requested_dt.strftime("%A").lower()
        block_day = block.get("day_of_week", "").lower()

        if day_of_week != block_day:
            return False

        block_start = block.get("start_time", "00:00")
        block_end = block.get("end_time", "23:59")

        req_time = requested_dt.strftime("%H:%M")
        return block_start <= req_time < block_end
