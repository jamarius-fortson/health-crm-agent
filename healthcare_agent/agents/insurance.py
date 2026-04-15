"""
Insurance Agent — Manages eligibility, benefits, and prior authorizations.

Responsibilities:
- Verifies insurance eligibility via clearinghouses.
- Checks coverage and benefits (co-pays, deductibles).
- Handles prior authorization requests (requires HITL).
- Syncs insurance records with the EHR.

Safety: Clinical medical necessity is NEVER determined by the agent.
All prior auth submissions MUST be reviewed by a human clinician (HITL).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from healthcare_agent.agents._base import BaseAgent
from healthcare_agent.models.domain import (
    InsurancePlan,
    EligibilityStatus,
    NetworkStatus,
)
from healthcare_agent.integrations.clearinghouses.change_healthcare import get_clearinghouse_client

logger = logging.getLogger(__name__)


class InsuranceAgent(BaseAgent):
    """
    Autonomous insurance agent for eligibility and benefits.
    
    PHI scope: Patient identity + Insurance credentials.
    """

    @property
    def agent_name(self) -> str:
        return "insurance_agent"

    @property
    def phi_scope_name(self) -> str:
        return "insurance"

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute insurance logic."""
        task = state.get("current_task", "")
        event_type = state.get("event_type", "")

        # Routing within the agent
        if task == "verify_insurance" or event_type == "verify_eligibility":
            return await self._verify_eligibility(state)
        elif task == "submit_prior_auth":
            return await self._submit_prior_auth(state)
        else:
             # Default: proceed from intake to eligibility
             if state.get("agent_results", {}).get("intake", {}).get("status") == "completed":
                 return await self._verify_eligibility(state)
                 
             return {
                "agent_results": {
                    "insurance": {
                        "status": "no_matching_task",
                        "task": task
                    }
                }
            }

    async def _verify_eligibility(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Verify patient's insurance eligibility."""
        patient_id = state.get("patient_id")
        # Extract insurance data from intake summary or state
        intake_res = state.get("agent_results", {}).get("intake", {})
        patient_data = intake_res.get("summary", {}) if intake_res else state.get("patient", {})
        
        # In a real system, we'd get payer_id from the patient record
        payer_id = patient_data.get("payer_id") or "BCBS"
        
        logger.info(f"Verifying eligibility for patient {patient_id} with payer {payer_id}")
        
        client = get_clearinghouse_client()
        try:
            raw_res = await client.verify_eligibility(patient_data, payer_id)
            
            # Map clearinghouse response to our domain model
            status = EligibilityStatus.ACTIVE if raw_res.get("eligibility_status") == "active" else EligibilityStatus.INACTIVE
            
            # Update state with insurance info
            return {
                "agent_results": {
                    "insurance": {
                        "status": "verified" if status == EligibilityStatus.ACTIVE else "failed",
                        "eligibility_status": status.value,
                        "payer_name": raw_res.get("payer_name"),
                        "plan_name": raw_res.get("plan_name"),
                        "copay": raw_res.get("copay"),
                        "deductible_remaining": raw_res.get("deductible_remaining"),
                    }
                },
                "next_node": "scheduling_agent" if status == EligibilityStatus.ACTIVE else "hitl_node",
                "current_task": "schedule_appointment" if status == EligibilityStatus.ACTIVE else state.get("current_task")
            }
        except Exception as e:
            logger.error(f"Eligibility verification failed: {e}")
            return {
                "agent_results": {
                    "insurance": {
                        "status": "error",
                        "error": str(e)
                    }
                },
                "next_node": "hitl_node"
            }
        finally:
            await client.close()

    async def _submit_prior_auth(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a prior authorization request.
        
        Mandatory HITL: All prior auths must be reviewed by the billing/clinical team.
        """
        patient_id = state.get("patient_id")
        auth_context = state.get("task_context", {}).get("prior_auth", {})
        
        logger.info(f"Initiating prior auth for patient {patient_id}")
        
        # Create HITL item for approval
        hitl_item = self.create_hitl_item(
            action_type="prior_auth_approval",
            description=f"Approve prior authorization for {auth_context.get('procedure_code')}",
            patient_id=patient_id,
            priority="normal",
            context={
                "auth_request": auth_context,
                "insurance_plan": state.get("agent_results", {}).get("insurance", {})
            }
        )
        
        return {
            "agent_results": {
                "insurance": {
                    "status": "waiting_for_approval",
                    "auth_request_id": auth_context.get("id")
                }
            },
            "hitl_queue": [hitl_item.to_dict()],
            "next_node": "hitl_node"
        }
