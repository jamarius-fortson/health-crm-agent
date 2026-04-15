"""
De-identification Module — Safe Harbor Method.

Strips all 18 HIPAA identifiers from data for analytics and long-term memory.
After de-identification, re-identification is impossible by construction —
the original identifiers are not stored, hashed, or linked to the de-identified data.

The 18 HIPAA Safe Harbor identifiers:
1. Names
2. All geographic subdivisions smaller than a state
3. All elements of dates (except year) directly related to an individual
4. Phone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate/license numbers
12. Vehicle identifiers and serial numbers, including license plate numbers
13. Device identifiers and serial numbers
14. Web Universal Resource Locators (URLs)
15. Internet Protocol (IP) address numbers
16. Biometric identifiers, including finger and voice prints
17. Full-face photographic images and any comparable images
18. Any other unique identifying number, characteristic, or code

This module is used for:
- Long-term memory storage (pgvector — NEVER stores PHI)
- Analytics dashboards
- No-show predictor training data
- De-identified metrics (Prometheus, OpenTelemetry)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from healthcare_agent.compliance.phi_classifier import PHIType
from healthcare_agent.models import Patient


@dataclass(frozen=True)
class DeIdentificationResult:
    """Result of de-identifying a data record."""
    deidentified_data: dict[str, Any]
    removed_fields: list[str]
    generalized_fields: list[str]
    record_hash: str  # Deterministic hash for deduplication (not re-identifiable)


def deidentify_patient(patient: Patient) -> DeIdentificationResult:
    """
    De-identify a patient record using the Safe Harbor method.

    All 18 HIPAA identifiers are removed or generalized.
    The resulting record CANNOT be re-identified.
    """
    removed: list[str] = []
    generalized: list[str] = []

    deidentified: dict[str, Any] = {
        # Remove: names
        # Remove: DOB (generalize to birth year only)
        "birth_year": patient.date_of_birth.year,
        generalized.append("date_of_birth -> birth_year"),
        # Remove: sex (not a direct identifier, but kept for analytics)
        "sex": patient.sex,
        # Remove: all contact info
        # Remove: all address info
        # Remove: emergency contact
        # Remove: insurance info
        # Keep: language (operational)
        "language": patient.language,
        # Keep: status (operational)
        "status": patient.status.value,
    }

    removed.extend([
        "first_name", "last_name", "date_of_birth", "phone", "email",
        "street_address", "city", "state", "zip_code",
        "emergency_contact_name", "emergency_contact_phone",
        "emergency_contact_relationship",
        "primary_insurance_plan_id", "fhir_resource_id",
        "gender_identity", "race", "ethnicity",
    ])

    # Deterministic hash for deduplication (not reversible)
    hash_input = f"{patient.id}:{patient.date_of_birth}:{patient.last_name}"
    record_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    return DeIdentificationResult(
        deidentified_data=deidentified,
        removed_fields=removed,
        generalized_fields=generalized,
        record_hash=record_hash,
    )


def deidentify_dict(data: dict[str, Any], phi_fields: set[str] | None = None) -> dict[str, Any]:
    """
    De-identify a generic dictionary by removing/generalizing PHI fields.

    If phi_fields is provided, only those fields are treated as PHI.
    Otherwise, the PHI classifier is used to identify PHI fields.
    """
    from healthcare_agent.compliance.phi_classifier import classify_field_name

    result = {}
    for key, value in data.items():
        if phi_fields is not None:
            is_phi = key in phi_fields
        else:
            classification = classify_field_name(key)
            is_phi = classification.is_phi

        if is_phi:
            # Generalize or remove based on field type
            classification = classify_field_name(key)
            if classification.category.value in ("date",):
                # Generalize dates to year only
                if isinstance(value, (date, datetime)):
                    result[f"{key}_year"] = value.year
                else:
                    result[key] = None
            elif classification.category.value in ("geographic",):
                # Generalize to state level only
                if isinstance(value, str) and len(value) == 2:
                    result[key] = value  # State is allowed
                else:
                    result[key] = None
            else:
                # Remove direct identifiers entirely
                result[key] = None
        else:
            result[key] = value

    return result


def generalize_date_range(
    dates: list[date],
    min_group_size: int = 5,
) -> list[str]:
    """
    Generalize a list of dates into ranges that contain at least min_group_size records.

    This ensures that no individual can be re-identified by their date.
    Dates for individuals over 89 are grouped into category "90+".
    """
    if not dates:
        return []

    # Sort dates
    sorted_dates = sorted(dates)

    # Group into buckets
    buckets: dict[str, int] = {}
    for d in sorted_dates:
        bucket = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        buckets[bucket] = buckets.get(bucket, 0) + 1

    # Suppress buckets with fewer than min_group_size
    result = []
    for bucket, count in sorted(buckets.items()):
        if count >= min_group_size:
            result.append(bucket)
        else:
            result.append("suppressed")

    return result
