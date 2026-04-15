"""
Test: PHI Scope Enforcement.

Verifies that:
1. PHI fields are correctly classified by the PHI classifier
2. Scope enforcement strips unauthorized PHI fields
3. Agents cannot access PHI fields outside their scope
4. Scope violations are detected and logged
"""

from __future__ import annotations

import pytest

from healthcare_agent.compliance.phi_classifier import (
    PHIClassification,
    PHICategory,
    classify_field_name,
    extract_phi_fields_from_model,
    scan_value_for_phi,
)
from healthcare_agent.compliance.minimum_necessary import (
    ALL_PHI_SCOPES,
    PHIScopeViolation,
    check_scope_violation,
    enforce_scope,
    SCHEDULING_SCOPE,
    INTAKE_SCOPE,
    INSURANCE_SCOPE,
    COMMUNICATIONS_SCOPE,
    CARE_COORDINATION_SCOPE,
)
from healthcare_agent.models import Patient


class TestPHIClassifier:
    """Test the PHI field classifier."""

    def test_name_fields_are_phi(self):
        """Names are PHI — HIPAA identifier #1."""
        for field in ["first_name", "last_name", "middle_name", "patient_name"]:
            result = classify_field_name(field)
            assert result.is_phi, f"{field} should be classified as PHI"
            assert result.category == PHICategory.NAME

    def test_address_fields_are_phi(self):
        """Geographic subdivisions are PHI — HIPAA identifier #2."""
        for field in ["street_address", "city", "state", "zip_code"]:
            result = classify_field_name(field)
            assert result.is_phi, f"{field} should be classified as PHI"
            assert result.category == PHICategory.GEOGRAPHIC

    def test_contact_fields_are_phi(self):
        """Phone and email are PHI — HIPAA identifiers #4, #6."""
        for field in ["phone", "phone_number", "email", "email_address"]:
            result = classify_field_name(field)
            assert result.is_phi, f"{field} should be classified as PHI"

    def test_date_fields_are_phi(self):
        """Dates related to individuals are PHI — HIPAA identifier #3."""
        for field in ["date_of_birth", "dob", "admission_date", "service_date"]:
            result = classify_field_name(field)
            assert result.is_phi, f"{field} should be classified as PHI"
            assert result.category == PHICategory.DATE

    def test_operational_fields_are_not_phi(self):
        """Operational fields should not be classified as PHI."""
        for field in ["status", "event_type", "created_at", "timezone", "appointment_type"]:
            result = classify_field_name(field)
            assert not result.is_phi, f"{field} should NOT be classified as PHI"

    def test_provider_id_is_operational(self):
        """Provider IDs are operational — they identify the clinician, not the patient."""
        result = classify_field_name("provider_id")
        assert not result.is_phi

    def test_patient_id_is_phi(self):
        """Patient IDs are PHI — they uniquely identify a patient."""
        result = classify_field_name("patient_id")
        assert result.is_phi

    def test_substring_match(self):
        """Substring matching catches nested field names."""
        result = classify_field_name("patient_phone_number")
        assert result.is_phi

    def test_scan_ssn_pattern(self):
        """Runtime scan detects SSN patterns."""
        results = scan_value_for_phi("My SSN is 123-45-6789")
        assert any(r.is_phi for r in results)
        assert any(r.category == PHICategory.SSN for r in results)

    def test_scan_phone_pattern(self):
        """Runtime scan detects phone numbers."""
        results = scan_value_for_phi("Call me at (555) 123-4567")
        assert any(r.is_phi for r in results)
        assert any(r.category == PHICategory.PHONE for r in results)

    def test_scan_email_pattern(self):
        """Runtime scan detects email addresses."""
        results = scan_value_for_phi("Email me at test@example.com")
        assert any(r.is_phi for r in results)
        assert any(r.category == PHICategory.EMAIL for r in results)

    def test_no_phi_on_clean_text(self):
        """Clean operational text should not trigger PHI detection."""
        results = scan_value_for_phi("The appointment is scheduled for Monday at 3 PM")
        # No PHI patterns in this text
        assert not any(r.is_phi for r in results)

    def test_model_field_extraction(self):
        """Extract PHI fields from a Pydantic model."""
        classifications = extract_phi_fields_from_model(Patient)
        assert "first_name" in classifications
        assert classifications["first_name"].is_phi
        assert "status" in classifications
        assert not classifications["status"].is_phi


class TestMinimumNecessary:
    """Test the minimum necessary enforcement."""

    def test_scheduling_scope_strips_clinical(self):
        """Scheduling scope should strip clinical-only fields."""
        data = {
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+15551234567",
            "email": "john@example.com",
            "date_of_birth": "1990-01-01",
            "chief_complaint": "Annual checkup",  # Not in scheduling scope
            "current_medications": ["Metformin"],  # Not in scheduling scope
            "status": "active",  # Operational — should pass through
        }
        scoped = SCHEDULING_SCOPE.strip_to_scope(data)
        assert scoped["first_name"] == "John"
        assert scoped["last_name"] == "Doe"
        assert scoped["phone"] == "+15551234567"
        assert scoped["email"] == "john@example.com"
        assert scoped["date_of_birth"] == "1990-01-01"
        assert scoped["status"] == "active"
        assert "chief_complaint" not in scoped
        assert "current_medications" not in scoped

    def test_communications_scope_is_minimal(self):
        """Communications scope should only have contact info."""
        data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "phone": "+15559876543",
            "email": "jane@example.com",
            "date_of_birth": "1985-05-15",  # Not in communications scope
            "street_address": "123 Main St",  # Not in communications scope
            "subscriber_id": "INS-12345",  # Not in communications scope
        }
        scoped = COMMUNICATIONS_SCOPE.strip_to_scope(data)
        assert scoped["first_name"] == "Jane"
        assert scoped["last_name"] == "Smith"
        assert scoped["phone"] == "+15559876543"
        assert scoped["email"] == "jane@example.com"
        assert "date_of_birth" not in scoped
        assert "street_address" not in scoped
        assert "subscriber_id" not in scoped

    def test_intake_scope_is_comprehensive(self):
        """Intake scope should include all demographics and insurance fields."""
        data = {
            "first_name": "Bob",
            "last_name": "Wilson",
            "phone": "+15551112222",
            "email": "bob@example.com",
            "date_of_birth": "1970-03-20",
            "street_address": "456 Oak Ave",
            "city": "Springfield",
            "state": "NY",
            "zip_code": "12345",
            "subscriber_id": "INS-99999",
            "group_number": "GRP-123",
            "payer_name": "Blue Cross",
            "chief_complaint": "Headache",
            "current_medications": ["Lisinopril"],
            "known_allergies": ["Penicillin"],
        }
        scoped = INTAKE_SCOPE.strip_to_scope(data)
        assert scoped["first_name"] == "Bob"
        assert scoped["city"] == "Springfield"
        assert scoped["subscriber_id"] == "INS-99999"
        assert scoped["chief_complaint"] == "Headache"
        assert scoped["current_medications"] == ["Lisinopril"]

    def test_enforce_scope_unknown_scope_raises(self):
        """Enforcing an unknown scope should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown PHI scope"):
            enforce_scope("nonexistent_scope", {"first_name": "Test"})

    def test_enforce_scope_wrong_role_raises(self):
        """Enforcing a scope with the wrong role should raise PermissionError."""
        with pytest.raises(PermissionError):
            enforce_scope("scheduling", {"first_name": "Test"}, role="insurance_agent")

    def test_enforce_scope_correct_role_passes(self):
        """Enforcing a scope with the correct role should succeed."""
        result = enforce_scope(
            "scheduling",
            {"first_name": "Test", "last_name": "User"},
            role="scheduling_agent",
        )
        assert result["first_name"] == "Test"

    def test_scope_violation_detected(self):
        """Accessing an unauthorized PHI field should be detected."""
        violation = check_scope_violation(
            scope_name="scheduling",
            accessed_field="chief_complaint",
            agent_name="SchedulingAgent",
        )
        assert violation is not None
        assert violation.violation_type == "unauthorized_phi_access"

    def test_no_violation_for_authorized_field(self):
        """Accessing an authorized PHI field should not trigger a violation."""
        violation = check_scope_violation(
            scope_name="scheduling",
            accessed_field="first_name",
            agent_name="SchedulingAgent",
        )
        assert violation is None

    def test_no_violation_for_non_phi_field(self):
        """Accessing a non-PHI field should not trigger a violation."""
        violation = check_scope_violation(
            scope_name="scheduling",
            accessed_field="status",
            agent_name="SchedulingAgent",
        )
        assert violation is None

    def test_all_scopes_are_defined(self):
        """All expected scopes should be defined."""
        expected_scopes = {
            "scheduling", "intake", "insurance",
            "communications", "care_coordination", "supervisor",
        }
        assert expected_scopes == set(ALL_PHI_SCOPES.keys())

    def test_scopes_have_distinct_phi_fields(self):
        """Different scopes should have different PHI field sets."""
        # Communications should have fewer fields than Intake
        assert len(COMMUNICATIONS_SCOPE.allowed_phi_fields) < len(INTAKE_SCOPE.allowed_phi_fields)
        # Scheduling should be different from Insurance
        assert SCHEDULING_SCOPE.allowed_phi_fields != INSURANCE_SCOPE.allowed_phi_fields
