"""
PHI Scope Guard — Enforces minimum necessary at the graph node level.

This module wraps every agent node with a PHI scope check:
1. Before the node runs: inject only the PHI fields the agent declared
2. After the node runs: verify the agent didn't access unauthorized PHI fields
3. On violation: raise an exception and write an audit incident

This is the structural enforcement of HIPAA's minimum necessary standard.
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable

from healthcare_agent.compliance.minimum_necessary import (
    ALL_PHI_SCOPES,
    PHIScope,
    PHIScopeViolation,
    check_scope_violation,
    enforce_scope,
)
from healthcare_agent.compliance.audit import log_audit
from healthcare_agent.models.audit import AuditEventType


def scope_phi_injection(
    scope_name: str,
    role: str | None = None,
) -> Callable:
    """
    Decorator that scopes PHI fields in a node's input.

    Before the agent node runs, this decorator strips all PHI fields
    not in the agent's declared scope from the input data.

    Usage:
        @scope_phi_injection("scheduling", role="scheduling_agent")
        async def scheduling_node(state: SupervisorState) -> dict:
            # state["patient"] contains only scheduling-scoped PHI
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            # Scope the patient data
            if "patient" in state and isinstance(state["patient"], dict):
                scoped_patient = enforce_scope(scope_name, state["patient"], role)
                state = {**state, "patient": scoped_patient}

            return await fn(state)
        return wrapper
    return decorator


def check_phi_scope_on_output(
    scope_name: str,
    agent_name: str,
    output_keys: list[str] | None = None,
) -> Callable:
    """
    Decorator that checks agent output for PHI scope violations.

    After the agent node returns, this decorator verifies that the agent
    didn't write to PHI fields outside its scope.

    Usage:
        @check_phi_scope_on_output("scheduling", agent_name="SchedulingAgent")
        async def scheduling_node(state: SupervisorState) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            result = await fn(state)

            # Check each key in the output for scope violations
            keys_to_check = output_keys or list(result.keys())
            for key in keys_to_check:
                violation = check_scope_violation(
                    scope_name=scope_name,
                    accessed_field=key,
                    agent_name=agent_name,
                )
                if violation is not None:
                    await _handle_scope_violation(violation)
                    raise PermissionError(violation.message)

            return result
        return wrapper
    return decorator


async def _handle_scope_violation(violation: PHIScopeViolation) -> None:
    """Handle a PHI scope violation: log audit event and alert."""
    await log_audit(
        event_type=AuditEventType.PHI_SCOPE_VIOLATION,
        action=f"PHI scope violation: {violation.field_name}",
        actor_id=violation.agent_name,
        details={
            "scope_name": violation.scope_name,
            "field_name": violation.field_name,
            "violation_type": violation.violation_type,
            "message": violation.message,
        },
    )


def combined_scope_guard(
    scope_name: str,
    agent_name: str,
    role: str | None = None,
) -> Callable:
    """
    Combined decorator that scopes input AND checks output.

    This is the recommended way to wrap agent nodes — it enforces
    minimum necessary on both input and output.
    """
    def decorator(fn: Callable) -> Callable:
        @scope_phi_injection(scope_name, role)
        @check_phi_scope_on_output(scope_name, agent_name)
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            return await fn(state)
        return wrapper
    return decorator
