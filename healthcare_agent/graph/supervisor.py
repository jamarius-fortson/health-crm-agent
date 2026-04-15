"""
Supervisor Agent — Root orchestrator for the LangGraph StateGraph.

The supervisor:
1. Receives inbound events and schedules the initial routing
2. Manages the shared state (SupervisorState)
3. Routes events to the appropriate agent node
4. Handles HITL pausing and resuming
5. Enforces cost guards (LLM spend cap)
6. Writes audit entries for every state transition
7. Activates the kill switch when requested

The graph structure:
```
                    ┌─────────────────┐
                    │   Supervisor     │
                    │   (entry/exit)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Router        │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────┐  ┌─────▼──────┐  ┌────▼─────────┐
     │   Intake     │  │ Scheduling  │  │  Insurance    │
     │   Agent      │  │   Agent     │  │   Agent       │
     └────────┬─────┘  └─────┬──────┘  └────┬─────────┘
              │              │              │
     ┌────────▼──────────────▼──────────────▼─────────┐
     │              Communications Agent                │
     └────────┬────────────────────────────────────────┘
              │
     ┌────────▼────────────────────────────────────────┐
     │           Care Coordination Agent                 │
     └────────┬────────────────────────────────────────┘
              │
     ┌────────▼────────┐
     │   HITL Node     │  (if approval needed)
     └────────┬────────┘
              │
              ▼
         (end or loop)
```
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from langgraph.graph import StateGraph, END

from healthcare_agent.graph.state import SupervisorState
from healthcare_agent.graph.router import route_event, route_by_task
from healthcare_agent.graph.router import (
    INTAKE_AGENT,
    SCHEDULING_AGENT,
    INSURANCE_AGENT,
    COMMUNICATIONS_AGENT,
    CARE_COORDINATION_AGENT,
    HITL_NODE,
    SUPERVISOR,
)
from healthcare_agent.graph.hitl import HITLQueue, get_hitl_queue
from healthcare_agent.agents.scheduling import SchedulingAgent
from healthcare_agent.agents.intake import IntakeAgent
from healthcare_agent.agents.insurance import InsuranceAgent
from healthcare_agent.agents.communications import CommunicationsAgent
from healthcare_agent.config import settings


class SupervisorAgent:
    """
    Root supervisor for the healthcare CRM agent graph.

    Manages the StateGraph lifecycle, routing, HITL, and cost guards.
    """

    def __init__(self) -> None:
        self.graph = self._build_graph()
        self._kill_switch = False
        self._daily_llm_cost = 0.0

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph StateGraph."""
        workflow = StateGraph(SupervisorState)

        # Add agent nodes (stubs — implemented in each agent module)
        workflow.add_node(INTAKE_AGENT, self._intake_node)
        workflow.add_node(SCHEDULING_AGENT, self._scheduling_node)
        workflow.add_node(INSURANCE_AGENT, self._insurance_node)
        workflow.add_node(COMMUNICATIONS_AGENT, self._communications_node)
        workflow.add_node(CARE_COORDINATION_AGENT, self._care_coordination_node)
        workflow.add_node(HITL_NODE, self._hitl_node)
        workflow.add_node(SUPERVISOR, self._supervisor_node)

        # Entry point
        workflow.set_entry_point(SUPERVISOR)

        # Conditional routing from supervisor
        workflow.add_conditional_edges(
            SUPERVISOR,
            self._route_from_supervisor,
            {
                INTAKE_AGENT: INTAKE_AGENT,
                SCHEDULING_AGENT: SCHEDULING_AGENT,
                INSURANCE_AGENT: INSURANCE_AGENT,
                COMMUNICATIONS_AGENT: COMMUNICATIONS_AGENT,
                CARE_COORDINATION_AGENT: CARE_COORDINATION_AGENT,
                HITL_NODE: HITL_NODE,
                SUPERVISOR: SUPERVISOR,
                END: END,
            },
        )

        # All agent nodes return to supervisor
        for node_name in [
            INTAKE_AGENT,
            SCHEDULING_AGENT,
            INSURANCE_AGENT,
            COMMUNICATIONS_AGENT,
            CARE_COORDINATION_AGENT,
        ]:
            workflow.add_edge(node_name, SUPERVISOR)

        # HITL node can end the graph (waiting for external resolution)
        workflow.add_edge(HITL_NODE, END)

        return workflow.compile()

    async def _supervisor_node(self, state: SupervisorState) -> dict:
        """Supervisor entry point — initializes state and routes."""
        updates: dict[str, Any] = {}

        # Check kill switch
        if self._kill_switch:
            updates["terminal"] = True
            updates["error"] = "Kill switch activated — all workflows paused"
            return updates

        # Check cost guard
        if self._daily_llm_cost >= settings.llm_daily_cost_cap_usd:
            updates["terminal"] = True
            updates["error"] = f"Daily LLM cost cap reached: ${self._daily_llm_cost:.2f}"
            return updates

        # Initialize HITL queue if not present
        if "hitl_queue" not in state:
            updates["hitl_queue"] = []
            updates["hitl_resolved"] = False

        # Initialize audit trail
        if "audit_entry_ids" not in state:
            updates["audit_entry_ids"] = []

        # Initialize cost tracking
        if "llm_cost_usd" not in state:
            updates["llm_cost_usd"] = 0.0
            updates["llm_call_count"] = 0

        return updates

    async def _intake_node(self, state: SupervisorState) -> dict:
        """Execute IntakeAgent logic."""
        agent = IntakeAgent()
        result = await agent.execute(state)
        # Handle automatic terminal state if no next node
        if "next_node" not in result and "terminal" not in result:
             result["terminal"] = True
        return result

    async def _scheduling_node(self, state: SupervisorState) -> dict:
        """Execute SchedulingAgent logic."""
        agent = SchedulingAgent()
        result = await agent.execute(state)
        # If the agent didn't set a next node, end the workflow
        if "next_node" not in result and "terminal" not in result:
             result["terminal"] = True
        return result

    async def _insurance_node(self, state: SupervisorState) -> dict:
        """Execute InsuranceAgent logic."""
        agent = InsuranceAgent()
        result = await agent.execute(state)
        # Handle automatic terminal state if no next node
        if "next_node" not in result and "terminal" not in result:
             result["terminal"] = True
        return result

    async def _communications_node(self, state: SupervisorState) -> dict:
        """Execute CommunicationsAgent logic."""
        agent = CommunicationsAgent()
        result = await agent.execute(state)
        # Handle automatic terminal state if no next node
        if "next_node" not in result and "terminal" not in result:
             result["terminal"] = True
        return result

    async def _care_coordination_node(self, state: SupervisorState) -> dict:
        """Stub — delegates to CareCoordinationAgent when implemented."""
        return {"agent_results": {"care_coordination": {"status": "not_implemented"}}}

    async def _hitl_node(self, state: SupervisorState) -> dict:
        """Handle HITL — pause workflow until human resolution."""
        return {"hitl_resolved": False}

    def _route_from_supervisor(self, state: SupervisorState) -> str:
        """Route from supervisor to the appropriate agent node."""
        if state.get("terminal"):
            return END

        # If HITL is active and not resolved, stay in HITL
        if state.get("hitl_queue"):
            queue = state["hitl_queue"]
            if isinstance(queue, list) and len(queue) > 0:
                pending = [
                    item for item in queue
                    if isinstance(item, dict) and item.get("status", "pending") == "pending"
                ]
                if pending:
                    return HITL_NODE

        # Route by task or event
        if state.get("next_node"):
            next_node = route_by_task(state)
        else:
            next_node = route_event(state)
            
        # Safety: avoid infinite loops back to supervisor node
        if next_node == SUPERVISOR:
            # If we don't know what to do, we might need HITL or just end
            if "error" in state:
                return END
            return HITL_NODE
            
        return next_node

    def activate_kill_switch(self) -> None:
        """Activate the kill switch — halts all workflows."""
        self._kill_switch = True

    def deactivate_kill_switch(self) -> None:
        """Deactivate the kill switch — resumes workflows."""
        self._kill_switch = False

    @property
    def is_killed(self) -> bool:
        return self._kill_switch

    async def invoke(self, initial_state: dict[str, Any]) -> dict:
        """
        Invoke the supervisor graph with an initial state.

        This is the main entry point for external callers.
        """
        result = await self.graph.ainvoke(initial_state)
        return result


# Global supervisor instance
_supervisor: SupervisorAgent | None = None


def get_supervisor() -> SupervisorAgent:
    """Get or create the global supervisor instance."""
    global _supervisor
    if _supervisor is None:
        _supervisor = SupervisorAgent()
    return _supervisor
