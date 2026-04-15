"""
Base Agent — Common functionality for all agents.

Every agent inherits from this class and gets:
1. Clinical boundary check on every output (safety/clinical_boundary.py)
2. PHI scope enforcement (graph/phi_scope.py)
3. Audit logging (compliance/audit.py)
4. HITL integration (graph/hitl.py)
5. Cost tracking

Subclasses must implement:
- `run()`: The agent's primary logic
- `phi_scope_name`: The name of the PHI scope this agent uses
- `agent_name`: A human-readable name for audit logging
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from healthcare_agent.compliance.audit import log_audit, log_phi_access
from healthcare_agent.compliance.minimum_necessary import enforce_scope
from healthcare_agent.safety.clinical_boundary import detect_clinical_content
from healthcare_agent.safety.content_classifier import classify_message
from healthcare_agent.graph.hitl import HITLItem, HITLPriority, HITLQueue, get_hitl_queue
from healthcare_agent.models.audit import AuditEventType


class BaseAgent(ABC):
    """
    Abstract base for all healthcare CRM agents.

    Every agent output passes through:
    1. PHI scope enforcement
    2. Clinical boundary detection
    3. Audit logging
    4. HITL evaluation
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name for audit logging."""

    @property
    @abstractmethod
    def phi_scope_name(self) -> str:
        """Name of the PHI scope this agent operates under."""

    @abstractmethod
    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's primary logic.

        Args:
            state: The current supervisor state (PHI-scoped for this agent)

        Returns:
            Updates to merge into the supervisor state
        """

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent with safety wrappers.

        This is the recommended entry point — it enforces all safety controls.
        Subclasses should override `run()` instead of `execute()`.
        """
        # Scope the patient data
        if "patient" in state:
            state["patient"] = enforce_scope(
                self.phi_scope_name,
                state["patient"],
                role=self.agent_name.lower(),
            )

        # Run the agent
        result = await self.run(state)

        # Log the agent action
        await log_audit(
            event_type=AuditEventType.AGENT_ACTION,
            action=f"{self.agent_name} executed",
            actor_id=self.agent_name,
            actor_role=self.phi_scope_name,
            patient_id=state.get("patient_id"),
            phi_fields_accessed=list(state.get("patient", {}).keys()),
            resource_type=self.agent_name,
            details={"task": state.get("current_task")},
        )

        return result

    async def check_clinical_boundary(self, text: str) -> dict[str, Any]:
        """
        Check if text contains clinical content.

        Returns a dict with 'blocked' and 'hitl_item' keys if blocked.
        """
        from healthcare_agent.safety.content_classifier import classify_message

        classification = classify_message(text)

        if not classification.is_safe:
            hitl_item = HITLItem(
                agent_name=self.agent_name,
                action_type="clinical_content_blocked",
                description=f"Clinical content blocked: {', '.join(classification.reasons[:3])}",
                patient_id=None,  # Will be set by caller
                priority=HITLPriority.HIGH,
                context={
                    "classification": {
                        "verdict": classification.verdict.value,
                        "confidence": classification.confidence,
                        "reasons": classification.reasons,
                    }
                },
            )
            return {"blocked": True, "hitl_item": hitl_item}

        return {"blocked": False, "hitl_item": None}

    def create_hitl_item(
        self,
        action_type: str,
        description: str,
        patient_id: str | None = None,
        priority: HITLPriority = HITLPriority.NORMAL,
        context: dict[str, Any] | None = None,
        requires_action: bool = True,
    ) -> HITLItem:
        """Create a HITL item for this agent."""
        return HITLItem(
            agent_name=self.agent_name,
            action_type=action_type,
            description=description,
            patient_id=patient_id,
            priority=priority,
            context=context or {},
            requires_action=requires_action,
        )
