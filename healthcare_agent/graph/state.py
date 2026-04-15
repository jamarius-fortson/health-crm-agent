"""
LangGraph Shared State for the Supervisor Graph.

This TypedDict defines the shared state that flows between all nodes
in the LangGraph StateGraph. It is structured to enforce:
1. PHI scoping — each node receives only the PHI fields it declared
2. HITL tracking — actions requiring human approval are surfaced
3. Audit trail — every state transition is linked to an audit entry
4. Minimum necessary — PHI is injected per-node, not globally

IMPORTANT: Patient PHI is NEVER embedded into long-term memory via this state.
Only de-identified operational patterns persist across encounters.
"""

from __future__ import annotations

from typing import Any, NotRequired, Annotated
import operator
from typing_extensions import TypedDict

from healthcare_agent.models import (
    Patient,
    Appointment,
    Message,
    InsurancePlan,
    IntakeSummary,
    Referral,
)
from healthcare_agent.models.audit import AuditEntry, AuditEventType
from healthcare_agent.compliance.minimum_necessary import PHIScope
from healthcare_agent.safety.red_flag_rules import RedFlagTrigger


class HITLItem(TypedDict):
    """An item in the Human-in-the-Loop queue."""
    id: str
    created_at: str
    agent_name: str
    action_type: str  # approval, escalation, review
    patient_id: str | None
    description: str
    requires_action: bool  # True if the graph is blocked waiting for HITL
    priority: str  # critical, high, normal, low
    context: dict[str, Any]  # Structured context for the human reviewer


class SupervisorState(TypedDict):
    """
    The shared state for the supervisor graph.

    PHI fields in this state are scoped per-agent. The supervisor node
    injects only the PHI fields that the target agent is authorized to see.
    """

    # --- Patient Context (PHI-scoped per agent) ---
    patient: NotRequired[dict[str, Any]]  # Patient data, scoped to current agent
    patient_id: NotRequired[str]

    # --- Current Task ---
    current_task: NotRequired[str]  # e.g., "schedule_appointment", "verify_insurance"
    task_context: NotRequired[dict[str, Any]]  # Structured task-specific context

    # --- Inbound Event ---
    event_type: NotRequired[str]  # e.g., "new_intake_form", "inbound_sms", "fhir_webhook"
    event_data: NotRequired[dict[str, Any]]  # Raw event payload

    # --- Agent Results ---
    agent_results: Annotated[dict[str, Any], operator.ior]

    # --- HITL Queue ---
    hitl_queue: Annotated[list[HITLItem], operator.add]
    hitl_resolved: NotRequired[bool]  # True if HITL item has been resolved

    # --- Clinic Configuration (OPERATIONAL — no PHI) ---
    clinic_config: NotRequired[dict[str, Any]]

    # --- Audit Trail ---
    audit_entry_ids: Annotated[list[str], operator.add]

    # --- Red Flag State ---
    red_flag_trigger: NotRequired[RedFlagTrigger | None]
    red_flag_escalated: NotRequired[bool]

    # --- Next Node Routing ---
    next_node: NotRequired[str]  # Which node to route to next
    terminal: NotRequired[bool]  # True if the workflow is complete

    # --- Cost Tracking ---
    llm_cost_usd: NotRequired[float]
    llm_call_count: NotRequired[int]

    # --- Error State ---
    error: NotRequired[str | None]
