"""
HIPAA-Compliant Email Client (Paubox).

Handles encrypted outbound emails without requiring patients to use portals/passwords.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from healthcare_agent.config import settings

logger = logging.getLogger(__name__)


class PauboxClient:
    """
    Client for Paubox Email API.
    
    Provides frictionless HIPAA-compliant email encryption.
    """

    def __init__(
        self,
        api_key: str = settings.paubox_api_key,
        from_email: str = settings.paubox_from_email,
    ):
        self.api_key = api_key
        self.from_email = from_email
        self.client = httpx.AsyncClient(
            base_url="https://api.paubox.net/v1/paubox_api",
            headers={"Authorization": f"Token token={self.api_key}"} if self.api_key else {}
        )

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a secure email."""
        if settings.env == "development" or not self.api_key:
            logger.info(f"[MOCK EMAIL] To: {to_email} | Subject: {subject} | Body: {body}")
            return {"source": "mock_paubox", "status": "sent"}

        url = "/messages"
        payload = {
            "data": {
                "message": {
                    "recipients": [to_email],
                    "header": {"subject": subject, "from": self.from_email},
                    "content": {
                        "text/plain": body,
                        "text/html": html_body or body
                    }
                }
            }
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Paubox Email failed: {e}")
            raise

    async def close(self):
        await self.client.aclose()


def get_email_client() -> PauboxClient:
    return PauboxClient()
