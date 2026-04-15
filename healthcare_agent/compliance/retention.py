"""
State-Specific Compliance Rules.

Configurable per-state rules for:
- Retention periods (varies by state, typically 5–10 years)
- Minor consent rules (some states allow minors to consent for specific services)
- Behavioral health special protections (42 CFR Part 2)
- State-specific breach notification timelines

This module provides the rules engine. Configuration comes from Settings.clinic_state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StateCode(str, Enum):
    """US state codes for compliance rule lookup."""
    AL = "AL"
    CA = "CA"
    FL = "FL"
    IL = "IL"
    NY = "NY"
    TX = "TX"
    # Add all 50 states + DC as needed


@dataclass(frozen=True)
class StateComplianceRules:
    """Compliance rules for a specific state."""
    state_code: str
    retention_years: int
    minor_consent_age: int = 18
    # States where minors can consent to specific services
    minor_can_consent_mental_health: bool = False
    minor_can_consent_substance_abuse: bool = False
    minor_can_consent_reproductive_health: bool = False
    # Breach notification timeline (hours)
    breach_notification_hours: int = 72  # Federal default is 60 days, but some states are stricter
    # 42 CFR Part 2 — substance use disorder records
    # Federal rule, but some states have additional protections
    additional_sud_protections: bool = False
    # Mental health records — some states require separate consent
    separate_mental_health_consent: bool = False
    notes: str = ""


# State-specific rules
# Source: State health department regulations, compiled from public sources
# MUST be reviewed by legal counsel before production use

_STATE_RULES: dict[str, StateComplianceRules] = {
    "CA": StateComplianceRules(
        state_code="CA",
        retention_years=7,  # California: 7 years from last discharge
        minor_consent_age=12,  # Minors 12+ can consent to mental health treatment
        minor_can_consent_mental_health=True,
        minor_can_consent_substance_abuse=True,
        minor_can_consent_reproductive_health=True,
        breach_notification_hours=72,  # California: 72 hours for state AG if >500 residents affected
        additional_sud_protections=False,
        separate_mental_health_consent=False,
        notes="California has strict minor consent laws for mental health (12+) and substance abuse (12+)",
    ),
    "NY": StateComplianceRules(
        state_code="NY",
        retention_years=6,  # New York: 6 years from last entry or 3 years from age 18, whichever is longer
        minor_consent_age=18,
        minor_can_consent_mental_health=False,
        minor_can_consent_substance_abuse=False,
        minor_can_consent_reproductive_health=True,
        breach_notification_hours=24,  # New York: 24 hours for state AG
        additional_sud_protections=True,
        separate_mental_health_consent=True,
        notes="NY has additional mental health record protections (MHL Article 33)",
    ),
    "TX": StateComplianceRules(
        state_code="TX",
        retention_years=7,  # Texas: 7 years from last encounter
        minor_consent_age=18,
        minor_can_consent_mental_health=False,
        minor_can_consent_substance_abuse=False,
        minor_can_consent_reproductive_health=True,
        breach_notification_hours=72,
        additional_sud_protections=False,
        separate_mental_health_consent=False,
    ),
    "FL": StateComplianceRules(
        state_code="FL",
        retention_years=5,  # Florida: 5 years from last encounter
        minor_consent_age=18,
        minor_can_consent_mental_health=True,
        minor_can_consent_substance_abuse=True,
        minor_can_consent_reproductive_health=False,
        breach_notification_hours=72,
        additional_sud_protections=False,
        separate_mental_health_consent=False,
    ),
}

# Federal default for states not yet configured
_FEDERAL_DEFAULT = StateComplianceRules(
    state_code="DEFAULT",
    retention_years=6,  # HIPAA requires 6 years from date of creation or last effective date
    minor_consent_age=18,
    breach_notification_hours=72,
    notes="Federal default — verify state-specific requirements with legal counsel",
)


def get_state_rules(state_code: str) -> StateComplianceRules:
    """Get compliance rules for a state."""
    return _STATE_RULES.get(state_code.upper(), _FEDERAL_DEFAULT)
