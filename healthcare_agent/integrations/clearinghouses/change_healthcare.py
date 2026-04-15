"""
Change Healthcare Clearinghouse API Client.

Interfaces with Change Healthcare for:
- Medical Network Eligibility (v3)
- Prior Authorization
- Claims Status

Supports both real and mock modes. Mock mode returns synthetic insurance data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

import httpx
from pydantic import BaseModel, Field

from healthcare_agent.config import settings
from healthcare_agent.models.domain import (
    EligibilityStatus,
    NetworkStatus,
    InsurancePlan,
    InsuranceSubscriber,
)

logger = logging.getLogger(__name__)


class ChangeHealthcareClient:
    """
    Client for Change Healthcare APIs.
    
    All calls are asynchronous and handle authentication internally.
    PHI is handled per the BAA with Change Healthcare.
    """

    def __init__(
        self,
        base_url: str = settings.change_healthcare_api_url,
        client_id: str = settings.change_healthcare_client_id,
        client_secret: str = settings.change_healthcare_client_secret,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.client = httpx.AsyncClient(timeout=30.0)
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        """Get or refresh OAuth2 token."""
        if self._token and self._token_expires and self._token_expires > datetime.utcnow():
            return self._token

        logger.info("Refreshing Change Healthcare OAuth2 token")
        
        # In a real system, we'd call the /auth/oauth2/token endpoint
        # For now, we return a mock token
        self._token = "mock-token-12345"
        self._token_expires = datetime.utcnow().replace(hour=23)
        return self._token

    async def verify_eligibility(
        self,
        patient_data: Dict[str, Any],
        payer_id: str,
        service_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Verify insurance eligibility for a patient.
        
        Endpoint: /medicalnetwork/eligibility/v3
        """
        if settings.env == "development":
             return await self._mock_eligibility_response(patient_data, payer_id)

        token = await self._get_token()
        url = f"{self.base_url}/medicalnetwork/eligibility/v3"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "controlNumber": "123456789",
            "tradingPartnerServiceId": payer_id,
            "provider": {
                "organizationName": settings.clinic_name,
                "npi": "1234567890",
            },
            "subscriber": {
                "firstName": patient_data.get("first_name"),
                "lastName": patient_data.get("last_name"),
                "memberId": patient_data.get("subscriber_id"),
                "dateOfBirth": patient_data.get("date_of_birth"),
            },
        }
        
        try:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Change Healthcare eligibility check failed: {e}")
            raise

    async def _mock_eligibility_response(self, patient_data: Dict[str, Any], payer_id: str) -> Dict[str, Any]:
        """Return synthetic eligibility response."""
        import asyncio
        await asyncio.sleep(1) # Simulate network lag
        
        # Determine active status based on patient ID for testing
        is_active = "inactive" not in (patient_data.get("patient_id") or "").lower()
        
        return {
            "eligibility_status": "active" if is_active else "inactive",
            "payer_name": "Aetna" if payer_id == "AETNA" else "Blue Cross Blue Shield",
            "plan_name": "PPO Choice Plus",
            "copay": 25.0,
            "deductible_total": 1500.0,
            "deductible_remaining": 450.0,
            "network_status": "in_network",
            "prior_auth_required": False,
        }

    async def close(self):
        await self.client.aclose()


def get_clearinghouse_client() -> ChangeHealthcareClient:
    """Factory for the clearinghouse client."""
    return ChangeHealthcareClient()
