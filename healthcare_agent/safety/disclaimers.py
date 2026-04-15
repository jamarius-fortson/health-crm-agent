"""
Disclaimers — Injected into every patient communication.

These disclaimers are appended to ALL outbound patient messages.
They are NEVER modified by LLMs, NEVER customized per patient,
and NEVER omitted. They are the system's constant reminder that
it is not a clinical tool.
"""

from __future__ import annotations

# ============================================================================
# Standard Disclaimer — appended to every patient-facing message
# ============================================================================

STANDARD_DISCLAIMER = (
    "\n\n---\n"
    "This is an automated message from {clinic_name}. "
    "This message is for operational purposes only and does not constitute medical advice. "
    "If you have a medical concern, please contact our office to speak with a clinician. "
    "If this is a medical emergency, call 911 or go to your nearest emergency room."
)

# ============================================================================
# Emergency Disclaimer — used when a red flag is triggered
# This is NOT the auto-response; this is appended to non-emergency messages
# when the system has flagged a patient for clinical review
# ============================================================================

EMERGENCY_FOOTER = (
    "\n\nIf you are experiencing a medical emergency, please call 911 "
    "or go to your nearest emergency room immediately."
)

# ============================================================================
# Intake Disclaimer — appended to intake confirmation messages
# ============================================================================

INTAKE_DISCLAIMER = (
    "\n\n---\n"
    "Thank you for completing your intake form. "
    "The information you provided will be reviewed by our clinical team before your visit. "
    "This system does not provide medical advice. If you have urgent medical concerns, "
    "please call our office directly. For emergencies, call 911."
)

# ============================================================================
# Prior Auth Disclaimer — appended to prior auth status notifications
# ============================================================================

PRIOR_AUTH_DISCLAIMER = (
    "\n\n---\n"
    "This notification is for informational purposes only. "
    "Insurance coverage determinations do not constitute medical advice "
    "or a recommendation for treatment. Please discuss your treatment options "
    "with your healthcare provider."
)


def format_disclaimer(
    disclaimer_type: str = "standard",
    clinic_name: str = "our clinic",
) -> str:
    """
    Format a disclaimer with clinic-specific information.

    The disclaimer text is NEVER modified beyond filling in the clinic name.
    No LLM processing, no customization, no tone adjustment.
    """
    if disclaimer_type == "standard":
        return STANDARD_DISCLAIMER.format(clinic_name=clinic_name)
    elif disclaimer_type == "emergency":
        return EMERGENCY_FOOTER
    elif disclaimer_type == "intake":
        return INTAKE_DISCLAIMER
    elif disclaimer_type == "prior_auth":
        return PRIOR_AUTH_DISCLAIMER
    else:
        return STANDARD_DISCLAIMER.format(clinic_name=clinic_name)


def append_disclaimer(message: str, disclaimer_type: str = "standard", clinic_name: str = "our clinic") -> str:
    """Append a disclaimer to a message. Idempotent — won't double-append."""
    disclaimer = format_disclaimer(disclaimer_type, clinic_name)
    if disclaimer in message:
        return message
    return message + disclaimer
