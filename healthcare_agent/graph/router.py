"""
Router — Determines which agent node should handle the current event.

The router examines the event type and current state to decide the next agent.
Routing is deterministic for known event types, with a fallback to the
supervisor for ambiguous cases.
"""

from __future__ import annotations

from healthcare_agent.graph.state import SupervisorState


# Agent node names
INTAKE_AGENT = "intake_agent"
SCHEDULING_AGENT = "scheduling_agent"
INSURANCE_AGENT = "insurance_agent"
COMMUNICATIONS_AGENT = "communications_agent"
CARE_COORDINATION_AGENT = "care_coordination_agent"
SUPERVISOR = "supervisor"
HITL_NODE = "hitl_node"
END_NODE = "__end__"

# Event type → agent mapping
_EVENT_ROUTING: dict[str, str] = {
    # Intake events
    "new_intake_form": INTAKE_AGENT,
    "intake_form_submitted": INTAKE_AGENT,
    "intake_demographics_update": INTAKE_AGENT,

    # Scheduling events
    "schedule_appointment": SCHEDULING_AGENT,
    "reschedule_appointment": SCHEDULING_AGENT,
    "cancel_appointment": SCHEDULING_AGENT,
    "appointment_reminder": SCHEDULING_AGENT,
    "no_show_detected": SCHEDULING_AGENT,
    "fhir_appointment_webhook": SCHEDULING_AGENT,

    # Insurance events
    "verify_eligibility": INSURANCE_AGENT,
    "prior_auth_request": INSURANCE_AGENT,
    "prior_auth_status_update": INSURANCE_AGENT,
    "eligibility_webhook": INSURANCE_AGENT,

    # Communications events
    "inbound_sms": COMMUNICATIONS_AGENT,
    "inbound_email": COMMUNICATIONS_AGENT,
    "inbound_portal_message": COMMUNICATIONS_AGENT,
    "send_reminder": COMMUNICATIONS_AGENT,
    "send_recall": COMMUNICATIONS_AGENT,
    "outbound_message_approved": COMMUNICATIONS_AGENT,

    # Care coordination events
    "check_referrals": CARE_COORDINATION_AGENT,
    "check_care_gaps": CARE_COORDINATION_AGENT,
    "transition_of_care": CARE_COORDINATION_AGENT,
    "referral_status_update": CARE_COORDINATION_AGENT,
}


def route_event(state: SupervisorState) -> str:
    """
    Route the current event to the appropriate agent node.

    Returns the node name to route to, or HITL_NODE if a red flag is active,
    or END_NODE if the workflow is terminal.
    """
    # Check for red flag — immediate HITL escalation
    if state.get("red_flag_escalated"):
        return HITL_NODE

    # Check HITL queue — if there's a critical item, route to HITL
    hitl_queue = state.get("hitl_queue", [])
    for item in hitl_queue:
        if isinstance(item, dict) and item.get("priority") == "critical":
            return HITL_NODE

    # Check if terminal
    if state.get("terminal"):
        return END_NODE

    # Route by event type
    event_type = state.get("event_type", "")
    agent = _EVENT_ROUTING.get(event_type)

    if agent is None:
        # Unknown event type — route to supervisor for manual handling
        return SUPERVISOR

    return agent


def route_by_task(state: SupervisorState) -> str:
    """
    Route based on the current task (used for multi-step workflows).

    After an agent completes its task, the supervisor sets next_task
    and this router determines the next agent.
    """
    next_node = state.get("next_node")
    if next_node:
        return next_node

    # Fall back to event-based routing
    return route_event(state)
