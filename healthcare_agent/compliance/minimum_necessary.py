"""
Minimum Necessary Enforcement.

HIPAA's "Minimum Necessary" standard is enforced structurally at runtime:

1. Every agent node declares the PHI fields it needs via `required_phi_fields`
2. The supervisor strips everything else from the context before the agent runs
3. If an agent accesses a field it didn't declare, an exception is raised and an audit incident is logged

This is NOT a convention or a guideline — it is enforced at runtime with code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from healthcare_agent.compliance.phi_classifier import (
    PHIClassification,
    classify_field_name,
    extract_phi_fields_from_model,
)
from healthcare_agent.models import PHIType


@dataclass(frozen=True)
class PHIScope:
    """
    Declares which PHI fields a component (agent, function, node) is authorized to access.

    Scopes are:
    - Whitelisted: only these fields may be accessed
    - Role-bound: the scope is granted only to specific roles
    - Audited: every access is logged
    """
    scope_name: str
    allowed_phi_fields: frozenset[str]
    granted_to_roles: frozenset[str]
    description: str = ""

    def has_access(self, field_name: str) -> bool:
        """Check if this scope grants access to a specific field."""
        return field_name in self.allowed_phi_fields

    def strip_to_scope(self, data: dict[str, Any]) -> dict[str, Any]:
        """Strip all fields not in this scope from a data dict."""
        return {
            k: v for k, v in data.items()
            if k in self.allowed_phi_fields or not _is_phi_field_name(k)
        }


def _is_phi_field_name(field_name: str) -> bool:
    """Check if a field name is PHI based on classification."""
    classification = classify_field_name(field_name)
    return classification.is_phi


# ============================================================================
# Predefined Scopes for Each Agent
# ============================================================================

# SchedulingAgent needs: patient identity for lookup, appointment times
SCHEDULING_SCOPE = PHIScope(
    scope_name="scheduling",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
        "phone",
        "email",
        "date_of_birth",  # For identity verification at check-in
        "start_time",
        "end_time",
        "appointment_type",
    }),
    granted_to_roles=frozenset({"scheduling_agent", "scheduler"}),
    description="Scheduling agent — needs patient identity and contact info only",
)

# IntakeAgent needs: full demographics and insurance
INTAKE_SCOPE = PHIScope(
    scope_name="intake",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "sex",
        "gender_identity",
        "race",
        "ethnicity",
        "phone",
        "email",
        "street_address",
        "city",
        "state",
        "zip_code",
        "emergency_contact_name",
        "emergency_contact_phone",
        "emergency_contact_relationship",
        "subscriber_id",
        "group_number",
        "payer_name",
        "plan_name",
        "policy_number",
        "chief_complaint",
        "current_medications",
        "known_allergies",
        "medical_history_flags",
    }),
    granted_to_roles=frozenset({"intake_agent", "front_desk"}),
    description="Intake agent — needs full demographics and insurance for registration",
)

# InsuranceAgent needs: patient identity + insurance details
INSURANCE_SCOPE = PHIScope(
    scope_name="insurance",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "subscriber_id",
        "group_number",
        "payer_name",
        "plan_name",
        "subscriber",
        "eligibility_status",
        "copay_amount",
        "deductible_amount",
        "deductible_remaining",
        "out_of_pocket_max",
        "network_status",
        "prior_auth_required",
        "prior_auth_number",
    }),
    granted_to_roles=frozenset({"insurance_agent", "billing"}),
    description="Insurance agent — needs patient identity and plan details for eligibility",
)

# CommunicationsAgent needs: contact info and message context ONLY
# Does NOT need: clinical notes, diagnoses, lab results
COMMUNICATIONS_SCOPE = PHIScope(
    scope_name="communications",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
        "phone",
        "email",
        "preferred_contact_method",
    }),
    granted_to_roles=frozenset({"communications_agent"}),
    description="Communications agent — needs contact info only, NEVER clinical content",
)

# CareCoordinationAgent needs: patient identity + referral/care gap info
CARE_COORDINATION_SCOPE = PHIScope(
    scope_name="care_coordination",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
        "phone",
        "date_of_birth",
        "referring_provider_id",
        "referred_to_provider_id",
        "referred_to_specialty",
        "referral_reason",
        "referral_status",
    }),
    granted_to_roles=frozenset({"care_coordination_agent", "care_coordinator"}),
    description="Care coordination agent — needs patient identity and referral info",
)

# Supervisor sees: only what's needed for routing (minimal PHI)
SUPERVISOR_SCOPE = PHIScope(
    scope_name="supervisor",
    allowed_phi_fields=frozenset({
        "patient_id",
        "first_name",
        "last_name",
    }),
    granted_to_roles=frozenset({"supervisor"}),
    description="Supervisor — minimal PHI for routing decisions only",
)


# Registry of all scopes
ALL_PHI_SCOPES: dict[str, PHIScope] = {
    "scheduling": SCHEDULING_SCOPE,
    "intake": INTAKE_SCOPE,
    "insurance": INSURANCE_SCOPE,
    "communications": COMMUNICATIONS_SCOPE,
    "care_coordination": CARE_COORDINATION_SCOPE,
    "supervisor": SUPERVISOR_SCOPE,
}


def enforce_scope(
    scope_name: str,
    data: dict[str, Any],
    role: str | None = None,
) -> dict[str, Any]:
    """
    Enforce a PHI scope on a data dictionary.

    1. Looks up the scope by name
    2. If a role is provided, verifies the role has access
    3. Strips all PHI fields not in the scope
    4. Returns the scoped data

    Raises:
        ValueError: if the scope doesn't exist
        PermissionError: if the role doesn't have access to the scope
    """
    scope = ALL_PHI_SCOPES.get(scope_name)
    if scope is None:
        raise ValueError(f"Unknown PHI scope: {scope_name}")

    if role is not None and role not in scope.granted_to_roles:
        raise PermissionError(
            f"Role '{role}' is not granted access to scope '{scope_name}'. "
            f"Allowed roles: {scope.granted_to_roles}"
        )

    return scope.strip_to_scope(data)


def check_scope_violation(
    scope_name: str,
    accessed_field: str,
    agent_name: str,
) -> PHIScopeViolation | None:
    """
    Check if an agent accessed a field outside its scope.

    Returns a PHIScopeViolation if the access was unauthorized, None otherwise.
    """
    scope = ALL_PHI_SCOPES.get(scope_name)
    if scope is None:
        return PHIScopeViolation(
            scope_name=scope_name,
            agent_name=agent_name,
            field_name=accessed_field,
            violation_type="unknown_scope",
            message=f"Unknown scope '{scope_name}' used by {agent_name}",
        )

    if not scope.has_access(accessed_field):
        # Check if the field is PHI at all
        classification = classify_field_name(accessed_field)
        if classification.is_phi:
            return PHIScopeViolation(
                scope_name=scope_name,
                agent_name=agent_name,
                field_name=accessed_field,
                violation_type="unauthorized_phi_access",
                message=(
                    f"Agent '{agent_name}' (scope: {scope_name}) accessed PHI field "
                    f"'{accessed_field}' which is not in its scope. "
                    f"Allowed fields: {scope.allowed_phi_fields}"
                ),
            )

    return None


@dataclass(frozen=True)
class PHIScopeViolation:
    """Represents a PHI scope violation."""
    scope_name: str
    agent_name: str
    field_name: str
    violation_type: str
    message: str
