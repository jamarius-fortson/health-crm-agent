"""
Test: BAA Endpoint Enforcement.

Verifies that:
1. Only BAA-covered endpoints are allowed
2. Non-BAA endpoints are blocked
3. The registry is correctly configured
4. LLM endpoints are especially restricted
"""

from __future__ import annotations

import pytest

from healthcare_agent.compliance.baa_registry import (
    BAAEndpoint,
    BAARegistry,
    BAAServiceType,
)


class TestBAARegistry:
    """Test the BAA endpoint registry."""

    def test_llm_endpoints_are_registered(self):
        """AWS Bedrock and Azure OpenAI should be in the LLM allowlist."""
        llm_names = BAARegistry.llm_endpoint_names()
        assert "aws-bedrock-anthropic" in llm_names
        assert "azure-openai" in llm_names

    def test_messaging_endpoints_are_registered(self):
        """Twilio and Paubox should be in the messaging allowlist."""
        messaging = BAARegistry.endpoints_by_type(BAAServiceType.MESSAGING_SMS)
        assert len(messaging) > 0
        assert any(ep.name == "twilio-sms" for ep in messaging)

        email = BAARegistry.endpoints_by_type(BAAServiceType.MESSAGING_EMAIL)
        assert any(ep.name == "paubox-email" for ep in email)

    def test_clearinghouse_endpoints_are_registered(self):
        """Change Healthcare, Availity, and pVerify should be registered."""
        clearinghouses = BAARegistry.endpoints_by_type(BAAServiceType.CLEARINGHOUSE)
        names = [ep.name for ep in clearinghouses]
        assert "change-healthcare" in names
        assert "availity" in names
        assert "pverify" in names

    def test_all_endpoints_have_baa_document_id(self):
        """Every endpoint must have a BAA document ID reference."""
        for endpoint in BAARegistry.all_endpoints():
            assert endpoint.baa_document_id, f"{endpoint.name} has no BAA document ID"
            assert endpoint.baa_signed_date, f"{endpoint.name} has no BAA signed date"

    def test_all_endpoints_have_vendor_name(self):
        """Every endpoint must have a vendor name."""
        for endpoint in BAARegistry.all_endpoints():
            assert endpoint.vendor_name, f"{endpoint.name} has no vendor name"

    def test_url_match_baa_covered(self):
        """BAA-covered URLs should be recognized."""
        assert BAARegistry.is_baa_covered("https://bedrock-runtime.us-east-1.amazonaws.com")
        assert BAARegistry.is_baa_covered("https://my-resource.openai.azure.com")
        assert BAARegistry.is_baa_covered("https://api.twilio.com/2010-04-01/Accounts")
        assert BAARegistry.is_baa_covered("https://api.paubox.com/v1")
        assert BAARegistry.is_baa_covered("https://apis.changehealthcare.com/eligibility/v1")

    def test_non_baa_url_blocked(self):
        """Non-BAA URLs should NOT be recognized."""
        assert not BAARegistry.is_baa_covered("https://api.openai.com/v1/chat/completions")
        assert not BAARegistry.is_baa_covered("https://api.openrouter.ai/v1/chat")
        assert not BAARegistry.is_baa_covered("https://api.anthropic.com/v1/messages")  # Direct Anthropic, not via Bedrock
        assert not BAARegistry.is_baa_covered("https://some-random-service.example.com/api")

    def test_get_endpoint_for_url(self):
        """Should return the correct endpoint for a matching URL."""
        endpoint = BAARegistry.get_endpoint_for_url("https://api.twilio.com")
        assert endpoint is not None
        assert endpoint.name == "twilio-sms"

        endpoint = BAARegistry.get_endpoint_for_url("https://nonexistent.example.com")
        assert endpoint is None

    def test_llm_urls_require_baa(self):
        """LLM URLs must go through BAA-covered endpoints only."""
        # OpenAI direct — NOT allowed (no BAA for direct OpenAI API)
        assert not BAARegistry.is_baa_covered("https://api.openai.com/v1/chat/completions")
        # Bedrock — allowed (with BAA)
        assert BAARegistry.is_baa_covered("https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke")
        # Azure OpenAI — allowed (with BAA)
        assert BAARegistry.is_baa_covered("https://my-clinic-resource.openai.azure.com/openai/deployments/my-deployment/chat/completions?api-version=2024-02-01")

    def test_no_duplicate_endpoints(self):
        """No duplicate endpoint names in the registry."""
        all_names = [ep.name for ep in BAARegistry.all_endpoints()]
        assert len(all_names) == len(set(all_names)), "Duplicate endpoint names found"

    def test_all_endpoints_have_data_types(self):
        """Every endpoint must specify allowed data types."""
        for endpoint in BAARegistry.all_endpoints():
            assert endpoint.data_types_allowed, f"{endpoint.name} has no data types"
            assert len(endpoint.data_types_allowed) > 0
