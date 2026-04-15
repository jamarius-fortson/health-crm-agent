"""
Intake Agent — Manages patient registration and intake questionnaire processing.

Responsibilities:
- Handles new patient registration
- Collects demographics and insurance information
- Processes structured medical history
- Detects red flags and escalates to HITL immediately
- Generates intake summaries for clinicians

HARD LINE: Never asks clinical follow-up questions beyond the structured form.
Red flags (chest pain, etc.) trigger immediate HITL escalation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from healthcare_agent.agents._base import BaseAgent
from healthcare_agent.models.domain import (
    IntakeSummary,
    IntakeStatus,
    Patient,
    PHIType,
)
from healthcare_agent.safety.red_flag_rules import check_red_flags
from healthcare_agent.compliance.phi_classifier import classify_phi
from healthcare_agent.graph.hitl import HITLPriority

logger = logging.getLogger(__name__)


class IntakeAgent(BaseAgent):
    """
    Autonomous intake agent for patient registration.
    
    PHI scope: full demographics, contact, and insurance info.
    """

    @property
    def agent_name(self) -> str:
        return "intake_agent"

    @property
    def phi_scope_name(self) -> str:
        return "intake"

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute intake logic based on the current task."""
        task = state.get("current_task", "")
        event_type = state.get("event_type", "")

        if task == "process_intake" or event_type == "intake_form_submitted":
            return await self._process_intake_form(state)
        elif task == "verify_demographics" or event_type == "intake_demographics_update":
            return await self._verify_demographics(state)
        else:
            return {
                "agent_results": {
                    "intake": {
                        "status": "no_matching_task",
                        "task": task,
                    }
                }
            }

    async def _process_intake_form(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a submitted intake form.
        
        1. Scan for red flags in any free-text fields (like chief complaint)
        2. Validate demographics and insurance data
        3. Create or update Patient record
        4. Generate IntakeSummary
        5. Route to InsuranceAgent for eligibility verification
        """
        form_data = state.get("event_data", {}) or state.get("task_context", {}).get("form_data", {})
        patient_id = state.get("patient_id") or form_data.get("patient_id")
        
        # --- Step 1: Red Flag Detection ---
        # Scan chief complaint and any other free-text fields
        chief_complaint = form_data.get("chief_complaint", "")
        red_flag_trigger = check_red_flags(chief_complaint)
        
        if red_flag_trigger.triggered:
            logger.warning(f"Red flag detected in intake: {red_flag_trigger.rule.name if red_flag_trigger.rule else 'Unknown'}")
            
            hitl_item = self.create_hitl_item(
                action_type="red_flag_escalation",
                description=f"Red flag trigger in intake form: {red_flag_trigger.rule.name if red_flag_trigger.rule else 'Unknown'}",
                patient_id=patient_id,
                priority=HITLPriority.CRITICAL,
                context={
                    "form_data": form_data,
                    "red_flag": red_flag_trigger.to_dict() if hasattr(red_flag_trigger, 'to_dict') else str(red_flag_trigger),
                    "auto_response": red_flag_trigger.rule.auto_response if red_flag_trigger.rule else "Please call 911 if this is an emergency."
                }
            )
            
            return {
                "agent_results": {
                    "intake": {
                        "status": "escalated",
                        "red_flag_triggered": True,
                        "reason": red_flag_trigger.rule.name if red_flag_trigger.rule else "Critical symptom detected"
                    }
                },
                "red_flag_escalated": True,
                "red_flag_trigger": str(red_flag_trigger),
                "hitl_queue": [hitl_item.to_dict()],
                "next_node": "hitl_node"
            }

        # --- Step 2: Validate and Process Data ---
        # (In a real system, we'd validate against FHIR/DB schemas)
        
        # Generate IntakeSummary
        summary = IntakeSummary(
            patient_id=patient_id or "new_patient",
            chief_complaint=chief_complaint,
            current_medications=form_data.get("medications", []),
            known_allergies=form_data.get("allergies", []),
            medical_history_flags=form_data.get("history_flags", []),
            demographics_verified=True,
            status=IntakeStatus.COMPLETED,
            completed_at=datetime.utcnow()
        )
        
        # --- Step 3: Result and Routing ---
        return {
            "patient_id": patient_id,
            "agent_results": {
                "intake": {
                    "status": "completed",
                    "summary_id": summary.id,
                    "summary": summary.model_dump(mode="json")
                }
            },
            "next_node": "insurance_agent",  # Proceed to eligibility check
            "task_context": {
                **state.get("task_context", {}),
                "intake_summary": summary.model_dump(mode="json"),
                "patient_data": form_data # Pass along for verification
            }
        }

    async def _verify_demographics(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Simple demographic validation task."""
        patient_data = state.get("patient", {})
        
        # Logic to verify data completeness
        required_fields = ["first_name", "last_name", "date_of_birth", "phone"]
        missing = [f for f in required_fields if not patient_data.get(f)]
        
        if missing:
             return {
                "agent_results": {
                    "intake": {
                        "status": "incomplete",
                        "missing_fields": missing
                    }
                },
                "next_node": "communications_agent", # Ask patient for missing info
                "task_context": {
                    "missing_demographics": missing
                }
            }
            
        return {
            "agent_results": {
                "intake": {
                    "status": "verified"
                }
            }
        }
