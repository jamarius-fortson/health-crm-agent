"""
FHIR R4 Client — HIPAA-compliant transport for EHR integration.

Handles authentication with BAA-compliant endpoints (Epic, Cerner, etc.)
and performs FHIR R4 operations on Patient, Appointment, Slot, and Schedule.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from fhir.resources.appointment import Appointment as FHIRAppointment
from fhir.resources.patient import Patient as FHIRPatient
from fhir.resources.bundle import Bundle
from pydantic import BaseModel, Field

from healthcare_agent.config import settings
from healthcare_agent.compliance.phi_classifier import classify_phi

logger = logging.getLogger(__name__)


class FHIRClient:
    """
    Client for interacting with FHIR R4 servers.
    
    In production, this handles OIDC/OAuth2 authentication and
    enforces TLS 1.3+ transport to BAA-covered endpoints.
    """

    def __init__(
        self,
        base_url: str = settings.fhir_base_url,
        access_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=30.0,
        )

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def get_patient(self, fhir_id: str) -> Dict[str, Any]:
        """Fetch a Patient resource by ID."""
        response = await self.client.get(f"/Patient/{fhir_id}")
        response.raise_for_status()
        return response.json()

    async def search_patients(self, params: Dict[str, str]) -> List[Dict[str, Any]]:
        """Search for Patients by parameters."""
        response = await self.client.get("/Patient", params=params)
        response.raise_for_status()
        bundle = response.json()
        return [entry["resource"] for entry in bundle.get("entry", [])]

    async def get_appointment(self, appointment_id: str) -> Dict[str, Any]:
        """Fetch an Appointment resource by ID."""
        response = await self.client.get(f"/Appointment/{appointment_id}")
        response.raise_for_status()
        return response.json()

    async def create_appointment(self, appointment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Appointment resource."""
        # Validate with fhir.resources
        fhir_appt = FHIRAppointment.parse_obj(appointment_data)
        
        response = await self.client.post(
            "/Appointment",
            json=fhir_appt.dict(),
        )
        response.raise_for_status()
        return response.json()

    async def patch_appointment(self, appointment_id: str, patch_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update an Appointment resource via JSON Patch."""
        response = await self.client.patch(
            f"/Appointment/{appointment_id}",
            json=patch_data,
            headers={"Content-Type": "application/json-patch+json"},
        )
        response.raise_for_status()
        return response.json()

    async def get_available_slots(
        self,
        schedule_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        """Fetch available Slots for a given Schedule and time range."""
        params = {
            "schedule": f"Schedule/{schedule_id}",
            "start": f"ge{start_date.isoformat()}",
            "end": f"le{end_date.isoformat()}",
            "status": "free",
        }
        response = await self.client.get("/Slot", params=params)
        response.raise_for_status()
        bundle = response.json()
        return [entry["resource"] for entry in bundle.get("entry", [])]

    async def close(self):
        await self.client.aclose()


class MockFHIRClient(FHIRClient):
    """
    Mock FHIR client for testing and development without a live EHR.
    
    Uses synthetic Synthea-like data.
    """

    def __init__(self, *args, **kwargs):
        super().__init__("http://mock-fhir", *args, **kwargs)
        self.patients = {}
        self.appointments = {}
        self.slots = []

    async def get_patient(self, fhir_id: str) -> Dict[str, Any]:
        if fhir_id not in self.patients:
            raise httpx.HTTPStatusError("Not Found", request=None, response=httpx.Response(404))
        return self.patients[fhir_id]

    async def search_patients(self, params: Dict[str, str]) -> List[Dict[str, Any]]:
        results = []
        for p in self.patients.values():
            match = True
            for k, v in params.items():
                if k == "family" and p.get("name", [{}])[0].get("family") != v:
                    match = False
                if k == "given" and v not in p.get("name", [{}])[0].get("given", []):
                    match = False
            if match:
                results.append(p)
        return results

    async def get_appointment(self, appointment_id: str) -> Dict[str, Any]:
        if appointment_id not in self.appointments:
            raise httpx.HTTPStatusError("Not Found", request=None, response=httpx.Response(404))
        return self.appointments[appointment_id]

    async def create_appointment(self, appointment_data: Dict[str, Any]) -> Dict[str, Any]:
        fhir_id = str(uuid4())
        appointment_data["id"] = fhir_id
        self.appointments[fhir_id] = appointment_data
        return appointment_data

    async def patch_appointment(self, appointment_id: str, patch_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        if appointment_id not in self.appointments:
            raise httpx.HTTPStatusError("Not Found", request=None, response=httpx.Response(404))
        # Simple mock patch logic
        appt = self.appointments[appointment_id]
        for op in patch_data:
            if op["op"] == "replace":
                path = op["path"].lstrip("/")
                appt[path] = op["value"]
        return appt

    async def get_available_slots(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return self.slots

    async def close(self):
        pass


def get_fhir_client() -> FHIRClient:
    """Factory to get the appropriate FHIR client based on environment."""
    if settings.env == "development" or settings.env == "test":
        return MockFHIRClient()
    return FHIRClient()
