"""
PHI (Protected Health Information) Classifier.

Tags every data field as PHI or non-PHI based on the 18 HIPAA Safe Harbor identifiers:
1. Names
2. Geographic subdivisions smaller than a state
3. Dates (except year) directly related to an individual
4. Phone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate/license numbers
12. Vehicle identifiers and serial numbers
13. Device identifiers and serial numbers
14. Web URLs
15. IP addresses
16. Biometric identifiers
17. Full-face photographic images
18. Any other unique identifying number, characteristic, or code

This classifier works at TWO levels:
1. Static analysis: reads model field annotations (json_schema_extra={"phi_type": ...})
2. Runtime analysis: scans arbitrary data for PHI patterns

The static analysis is the PRIMARY enforcement mechanism. Runtime analysis is a safety net.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel


class PHICategory(str, Enum):
    """Categories of PHI for classification."""
    NAME = "name"
    GEOGRAPHIC = "geographic"
    DATE = "date"
    PHONE = "phone"
    EMAIL = "email"
    SSN = "ssn"
    MEDICAL_RECORD = "medical_record"
    INSURANCE = "insurance"
    ACCOUNT = "account"
    CERTIFICATE = "certificate"
    VEHICLE = "vehicle"
    DEVICE = "device"
    URL = "url"
    IP_ADDRESS = "ip_address"
    BIOMETRIC = "biometric"
    IMAGE = "image"
    OTHER_IDENTIFIER = "other_identifier"
    NOT_PHI = "not_phi"


@dataclass(frozen=True)
class PHIClassification:
    """Result of classifying a single field or value."""
    field_name: str | None
    is_phi: bool
    category: PHICategory
    confidence: float  # 0.0–1.0
    reason: str = ""


# ============================================================================
# Static PHI Field Registry — maps common field names to PHI categories
# ============================================================================

_PHI_FIELD_PATTERNS: dict[str, PHICategory] = {
    # Names
    "first_name": PHICategory.NAME,
    "last_name": PHICategory.NAME,
    "middle_name": PHICategory.NAME,
    "maiden_name": PHICategory.NAME,
    "full_name": PHICategory.NAME,
    "patient_name": PHICategory.NAME,
    "provider_name": PHICategory.NAME,
    "contact_name": PHICategory.NAME,

    # Geographic
    "street_address": PHICategory.GEOGRAPHIC,
    "address": PHICategory.GEOGRAPHIC,
    "city": PHICategory.GEOGRAPHIC,
    "state": PHICategory.GEOGRAPHIC,
    "zip_code": PHICategory.GEOGRAPHIC,
    "zip": PHICategory.GEOGRAPHIC,
    "county": PHICategory.GEOGRAPHIC,
    "latitude": PHICategory.GEOGRAPHIC,
    "longitude": PHICategory.GEOGRAPHIC,

    # Dates (directly related to individual)
    "date_of_birth": PHICategory.DATE,
    "dob": PHICategory.DATE,
    "admission_date": PHICategory.DATE,
    "discharge_date": PHICategory.DATE,
    "service_date": PHICategory.DATE,
    "appointment_date": PHICategory.DATE,

    # Contact
    "phone": PHICategory.PHONE,
    "phone_number": PHICategory.PHONE,
    "mobile": PHICategory.PHONE,
    "fax": PHICategory.PHONE,
    "fax_number": PHICategory.PHONE,
    "email": PHICategory.EMAIL,
    "email_address": PHICategory.EMAIL,

    # Identifiers
    "ssn": PHICategory.SSN,
    "social_security": PHICategory.SSN,
    "medical_record_number": PHICategory.MEDICAL_RECORD,
    "mrn": PHICategory.MEDICAL_RECORD,
    "member_id": PHICategory.INSURANCE,
    "subscriber_id": PHICategory.INSURANCE,
    "policy_number": PHICategory.INSURANCE,
    "group_number": PHICategory.INSURANCE,
    "account_number": PHICategory.ACCOUNT,
    "license_number": PHICategory.CERTIFICATE,
    "npi": PHICategory.CERTIFICATE,
    "dea_number": PHICategory.CERTIFICATE,

    # Patient linkage
    "patient_id": PHICategory.OTHER_IDENTIFIER,
    "encounter_id": PHICategory.OTHER_IDENTIFIER,
    "appointment_id": PHICategory.OTHER_IDENTIFIER,

    # Clinical (PHI by association with individual)
    "diagnosis": PHICategory.OTHER_IDENTIFIER,
    "procedure": PHICategory.OTHER_IDENTIFIER,
    "medication": PHICategory.OTHER_IDENTIFIER,
    "allergy": PHICategory.OTHER_IDENTIFIER,
    "chief_complaint": PHICategory.OTHER_IDENTIFIER,
}

# Fields that are NEVER PHI
_NON_PHI_FIELD_PATTERNS: set[str] = {
    "id",  # System-generated UUIDs without patient linkage
    "event_type",
    "status",
    "created_at",
    "updated_at",
    "timezone",
    "language",
    "preferred_contact_method",
    "appointment_type",
    "appointment_type_display",
    "visit_type",
    "location",
    "duration_minutes",
    "max_appointments_per_day",
    "overbook_high_risk_no_show",
    "no_show_risk_threshold",
    "clinic_name",
    "clinic_phone",
    "provider_id",  # Provider IDs (not patient-linked) are operational
    "resource_type",
    "action",
    "actor_id",
    "actor_role",
    "session_id",
    "ip_address",  # The IP of the staff member, not the patient
    "user_agent",
}


def classify_field_name(field_name: str, value: Any = None) -> PHIClassification:
    """
    Classify a single field based on its name.

    This is used for static analysis of model fields and runtime inspection
    of arbitrary data structures.
    """
    name_lower = field_name.lower().strip()

    # Check non-PHI allowlist first
    if name_lower in _NON_PHI_FIELD_PATTERNS:
        return PHIClassification(
            field_name=field_name,
            is_phi=False,
            category=PHICategory.NOT_PHI,
            confidence=0.95,
            reason="Field is in the non-PHI operational allowlist",
        )

    # Check PHI patterns
    # Exact match
    if name_lower in _PHI_FIELD_PATTERNS:
        return PHIClassification(
            field_name=field_name,
            is_phi=True,
            category=_PHI_FIELD_PATTERNS[name_lower],
            confidence=0.99,
            reason=f"Field name '{field_name}' matches PHI pattern",
        )

    # Substring match (for nested or suffixed fields)
    for pattern, category in _PHI_FIELD_PATTERNS.items():
        if pattern in name_lower:
            return PHIClassification(
                field_name=field_name,
                is_phi=True,
                category=category,
                confidence=0.80,
                reason=f"Field name '{field_name}' contains PHI pattern '{pattern}'",
            )

    # Check for ID fields that link to patients
    if name_lower.endswith("_id") and "patient" in name_lower:
        return PHIClassification(
            field_name=field_name,
            is_phi=True,
            category=PHICategory.OTHER_IDENTIFIER,
            confidence=0.95,
            reason="Field is a patient-linked identifier",
        )

    # Default: not PHI (but with low confidence — recommend manual review)
    return PHIClassification(
        field_name=field_name,
        is_phi=False,
        category=PHICategory.NOT_PHI,
        confidence=0.50,
        reason=f"Field name '{field_name}' not recognized as PHI — manual review recommended",
    )


def extract_phi_fields_from_model(model: type[BaseModel]) -> dict[str, PHIClassification]:
    """
    Extract PHI classifications from a Pydantic model's field annotations.

    Reads json_schema_extra.phi_type annotations for authoritative classification.
    Falls back to field name analysis for unannotated fields.
    """
    results: dict[str, PHIClassification] = {}

    for field_name, field_info in model.model_fields.items():
        # Check for explicit phi_type annotation
        json_schema_extra = field_info.json_schema_extra
        if isinstance(json_schema_extra, dict) and "phi_type" in json_schema_extra:
            phi_type = json_schema_extra["phi_type"]
            is_phi = phi_type != "operational"
            results[field_name] = PHIClassification(
                field_name=field_name,
                is_phi=is_phi,
                category=PHICategory.NOT_PHI if not is_phi else PHICategory.OTHER_IDENTIFIER,
                confidence=1.0,
                reason=f"Explicit phi_type annotation: {phi_type}",
            )
        else:
            # Fall back to field name analysis
            results[field_name] = classify_field_name(field_name)

    return results


# ============================================================================
# Runtime PHI Detection — scans string values for PHI patterns
# ============================================================================

_PHI_VALUE_PATTERNS: list[tuple[re.Pattern, PHICategory, str]] = [
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), PHICategory.SSN, "SSN pattern"),
    # Phone numbers
    (re.compile(r"\b\+?1?\s*\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"), PHICategory.PHONE, "Phone number pattern"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), PHICategory.EMAIL, "Email pattern"),
    # Date of birth context (when preceded by DOB-like keywords)
    (re.compile(r"(?:dob|date.?of.?birth|born)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", re.IGNORECASE), PHICategory.DATE, "DOB with value"),
]


def scan_value_for_phi(value: str, max_length: int = 1000) -> list[PHIClassification]:
    """
    Scan a string value for PHI patterns.

    This is a runtime safety net — the primary classification comes from
    field name analysis and model annotations.
    """
    results: list[PHIClassification] = []
    truncated = value[:max_length]

    for pattern, category, reason in _PHI_VALUE_PATTERNS:
        if pattern.search(truncated):
            results.append(PHIClassification(
                field_name=None,
                is_phi=True,
                category=category,
                confidence=0.90,
                reason=reason,
            ))

    return results


def classify_phi(data: Any) -> bool:
    """
    Simplified check: returns True if the data (dict, list, or string) contains likely PHI.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if classify_field_name(k).is_phi:
                return True
            if classify_phi(v):
                return True
    elif isinstance(data, list):
        for item in data:
            if classify_phi(item):
                return True
    elif isinstance(data, str):
        if scan_value_for_phi(data):
            return True
    return False
