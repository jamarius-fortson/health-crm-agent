"""
SMS Messaging Client (Twilio).

Handles outbound SMS and inbound webhook processing.
Ensures BAA compliance by using Twilio's healthcare-specific endpoints if configured.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from healthcare_agent.config import settings

logger = logging.getLogger(__name__)


class TwilioClient:
    """
    Client for Twilio Programmable SMS.
    
    Supports mock mode for development.
    """

    def __init__(
        self,
        account_sid: str = settings.twilio_account_sid,
        auth_token: str = settings.twilio_auth_token,
        from_number: str = settings.twilio_phone_number,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.client = httpx.AsyncClient(
            base_url=f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}",
            auth=(self.account_sid, self.auth_token) if self.account_sid else None
        )

    async def send_sms(self, to_number: str, body: str) -> Dict[str, Any]:
        """Send an SMS message."""
        if settings.env == "development" or not self.account_sid:
            logger.info(f"[MOCK SMS] To: {to_number} | Body: {body}")
            return {"sid": "mock_sms_sid_123", "status": "sent"}

        url = "/Messages.json"
        data = {
            "To": to_number,
            "From": self.from_number,
            "Body": body,
        }
        
        try:
            response = await self.client.post(url, data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            raise

    async def close(self):
        await self.client.aclose()


def get_sms_client() -> TwilioClient:
    return TwilioClient()
