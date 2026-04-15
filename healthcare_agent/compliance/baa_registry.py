"""
BAA (Business Associate Agreement) Endpoint Registry.

This is the ONLY allowlist of external service endpoints that may receive PHI.
Every outbound HTTP request to an external service is checked against this registry.
Requests to non-registered endpoints are blocked at the egress proxy.

Adding an endpoint requires:
1. A signed BAA with the vendor on file
2. A code change (not just config)
3. Reference to the BAA document ID
4. Passing compliance tests

LLM endpoints are especially restricted — they cannot be added via config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class BAAServiceType(str, Enum):
    LLM = "llm"
    MESSAGING_SMS = "messaging_sms"
    MESSAGING_EMAIL = "messaging_email"
    MESSAGING_VOICE = "messaging_voice"
    CLEARINGHOUSE = "clearinghouse"
    CLOUD_PROVIDER = "cloud_provider"
    EHR_FHIR = "ehr_fhir"


@dataclass(frozen=True)
class BAAEndpoint:
    """A single BAA-covered endpoint."""
    name: str
    service_type: BAAServiceType
    base_url: str
    vendor_name: str
    baa_document_id: str
    baa_signed_date: str  # ISO date
    data_types_allowed: list[str]  # What PHI/data types may be sent
    notes: str = ""


class BAARegistry:
    """
    Immutable registry of BAA-covered endpoints.

    This is a code-level allowlist — not a configuration file.
    Adding an endpoint requires a code change and PR review.
    """

    # =========================================================================
    # LLM ENDPOINTS — HIGHEST RESTRICTION
    # Only these LLM endpoints may ever receive PHI.
    # =========================================================================

    _LLM_ENDPOINTS: ClassVar[list[BAAEndpoint]] = [
        BAAEndpoint(
            name="aws-bedrock-anthropic",
            service_type=BAAServiceType.LLM,
            base_url="https://bedrock-runtime.{region}.amazonaws.com",
            vendor_name="Amazon Web Services",
            baa_document_id="AWS-BAA-2024-001",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_limited", "operational"],
            notes="AWS BAA covers Bedrock. PHI must use minimum-necessary scope.",
        ),
        BAAEndpoint(
            name="azure-openai",
            service_type=BAAServiceType.LLM,
            base_url="https://{resource}.openai.azure.com",
            vendor_name="Microsoft Corporation",
            baa_document_id="MSFT-BAA-2024-002",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_limited", "operational"],
            notes="Azure BAA covers OpenAI Service. HIPAA eligibility requires specific SKU.",
        ),
    ]

    # =========================================================================
    # MESSAGING ENDPOINTS
    # =========================================================================

    _MESSAGING_ENDPOINTS: ClassVar[list[BAAEndpoint]] = [
        BAAEndpoint(
            name="twilio-sms",
            service_type=BAAServiceType.MESSAGING_SMS,
            base_url="https://api.twilio.com",
            vendor_name="Twilio Inc.",
            baa_document_id="TWILIO-BAA-2024-003",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_limited", "operational"],
            notes="Twilio HIPAA-eligible plan required. BAA must be signed.",
        ),
        BAAEndpoint(
            name="twilio-voice",
            service_type=BAAServiceType.MESSAGING_VOICE,
            base_url="https://api.twilio.com",
            vendor_name="Twilio Inc.",
            baa_document_id="TWILIO-BAA-2024-003",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_limited", "operational"],
            notes="Same BAA as SMS. Voice calls for appointment reminders.",
        ),
        BAAEndpoint(
            name="paubox-email",
            service_type=BAAServiceType.MESSAGING_EMAIL,
            base_url="https://api.paubox.com",
            vendor_name="Paubox Inc.",
            baa_document_id="PAUBOX-BAA-2024-004",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_full", "operational"],
            notes="Paubox is HIPAA-native. BAA included in service agreement.",
        ),
    ]

    # =========================================================================
    # CLEARINGHOUSE ENDPOINTS
    # =========================================================================

    _CLEARINGHOUSE_ENDPOINTS: ClassVar[list[BAAEndpoint]] = [
        BAAEndpoint(
            name="change-healthcare",
            service_type=BAAServiceType.CLEARINGHOUSE,
            base_url="https://apis.changehealthcare.com",
            vendor_name="Change Healthcare (Optum)",
            baa_document_id="CH-BAA-2024-005",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_full", "operational"],
            notes="X12 270/271 eligibility, 276/276 claim status. BAA required.",
        ),
        BAAEndpoint(
            name="availity",
            service_type=BAAServiceType.CLEARINGHOUSE,
            base_url="https://api.availity.com",
            vendor_name="Availity LLC",
            baa_document_id="AVAILITY-BAA-2024-006",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_full", "operational"],
            notes="Eligibility and claims. BAA required.",
        ),
        BAAEndpoint(
            name="pverify",
            service_type=BAAServiceType.CLEARINGHOUSE,
            base_url="https://api.pverify.com",
            vendor_name="pVerify LLC",
            baa_document_id="PVERIFY-BAA-2024-007",
            baa_signed_date="2024-01-01",
            data_types_allowed=["phi_full", "operational"],
            notes="Eligibility verification. BAA required.",
        ),
    ]

    # =========================================================================
    # CLOUD PROVIDERS
    # =========================================================================

    _CLOUD_ENDPOINTS: ClassVar[list[BAAEndpoint]] = [
        BAAEndpoint(
            name="aws-kms",
            service_type=BAAServiceType.CLOUD_PROVIDER,
            base_url="https://kms.{region}.amazonaws.com",
            vendor_name="Amazon Web Services",
            baa_document_id="AWS-BAA-2024-001",
            baa_signed_date="2024-01-01",
            data_types_allowed=["encrypted_phi"],
            notes="KMS for envelope encryption. Covered under same BAA as Bedrock.",
        ),
        BAAEndpoint(
            name="aws-s3",
            service_type=BAAServiceType.CLOUD_PROVIDER,
            base_url="https://s3.{region}.amazonaws.com",
            vendor_name="Amazon Web Services",
            baa_document_id="AWS-BAA-2024-001",
            baa_signed_date="2024-01-01",
            data_types_allowed=["encrypted_phi"],
            notes="S3 for encrypted file storage. Covered under same BAA as Bedrock.",
        ),
    ]

    # =========================================================================
    # COMBINED LOOKUP
    # =========================================================================

    @classmethod
    def all_endpoints(cls) -> list[BAAEndpoint]:
        """Return all BAA-covered endpoints."""
        return (
            cls._LLM_ENDPOINTS
            + cls._MESSAGING_ENDPOINTS
            + cls._CLEARINGHOUSE_ENDPOINTS
            + cls._CLOUD_ENDPOINTS
        )

    @classmethod
    def endpoints_by_type(cls, service_type: BAAServiceType) -> list[BAAEndpoint]:
        """Return endpoints by service type."""
        return [ep for ep in cls.all_endpoints() if ep.service_type == service_type]

    @classmethod
    def is_baa_covered(cls, url: str) -> bool:
        """
        Check if a URL matches a BAA-covered endpoint.

        This does a prefix match against the base_url of every registered endpoint.
        """
        url_lower = url.lower().rstrip("/")
        for endpoint in cls.all_endpoints():
            base_lower = endpoint.base_url.lower().rstrip("/")
            # Handle templated URLs (e.g., {region})
            if "{" in base_lower:
                # Extract the domain pattern
                import re
                pattern = re.sub(r"\{[^}]+\}", r"[^/]+", base_lower)
                if re.match(pattern, url_lower):
                    return True
            else:
                if url_lower.startswith(base_lower):
                    return True
        return False

    @classmethod
    def get_endpoint_for_url(cls, url: str) -> BAAEndpoint | None:
        """Get the BAA endpoint that covers a URL, or None."""
        for endpoint in cls.all_endpoints():
            base_lower = endpoint.base_url.lower().rstrip("/")
            url_lower = url.lower().rstrip("/")
            if "{" in base_lower:
                import re
                pattern = re.sub(r"\{[^}]+\}", r"[^/]+", base_lower)
                if re.match(pattern, url_lower):
                    return endpoint
            else:
                if url_lower.startswith(base_lower):
                    return endpoint
        return None

    @classmethod
    def llm_endpoint_names(cls) -> list[str]:
        """Return the names of all allowed LLM endpoints."""
        return [ep.name for ep in cls._LLM_ENDPOINTS]
