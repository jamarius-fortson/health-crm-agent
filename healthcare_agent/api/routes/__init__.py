from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from healthcare_agent.database import get_db
from healthcare_agent.models.database import AppointmentDB, PatientDB
from healthcare_agent.agents.scheduling import SchedulingAgent

router = APIRouter()

class PatientRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str | None = None
    email: str | None = None

class ScheduleRequest(BaseModel):
    patient_id: str
    appointment_type: str
    preferred_date: str  # ISO format
    notes: str | None = None

@router.post("/patients")
async def create_patient(
    request: PatientRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new patient."""
    try:
        patient = PatientDB(
            first_name=request.first_name,
            last_name=request.last_name,
            date_of_birth=request.date_of_birth,
            phone=request.phone,
            email=request.email,
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)
        
        return {
            "status": "created",
            "patient_id": str(patient.id),
            "message": f"Patient {request.first_name} {request.last_name} created"
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule")
async def schedule_appointment(
    request: ScheduleRequest,
    db: AsyncSession = Depends(get_db)
):
    """Schedule an appointment using the scheduling agent."""
    try:
        # Check if patient exists
        patient = await db.get(PatientDB, request.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # For now, create a basic appointment
        # TODO: Integrate with full agent logic
        appointment = AppointmentDB(
            patient_id=request.patient_id,
            provider_id="default_provider",  # TODO: determine from logic
            appointment_type=request.appointment_type,
            appointment_type_display=request.appointment_type.replace("_", " ").title(),
            start_time=datetime.fromisoformat(request.preferred_date),
            end_time=datetime.fromisoformat(request.preferred_date),  # TODO: calculate duration
            status="scheduled"
        )
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        
        return {
            "status": "scheduled",
            "appointment_id": str(appointment.id),
            "message": f"Appointment scheduled for patient {request.patient_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Add routes here