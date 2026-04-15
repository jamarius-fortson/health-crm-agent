"""
SQLAlchemy database models for the healthcare CRM agent.

These models mirror the Pydantic domain models but are designed for database persistence.
PHI fields are still annotated for compliance enforcement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class PatientDB(Base):
    """SQLAlchemy model for Patient."""
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fhir_resource_id = Column(String(255), nullable=True)

    # Demographics (PHI)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=True)
    gender_identity = Column(String(50), nullable=True)
    race = Column(String(50), nullable=True)
    ethnicity = Column(String(50), nullable=True)

    # Contact (PHI)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    preferred_contact_method = Column(String(20), default="phone")

    # Address (PHI)
    street_address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(2), nullable=True)
    zip_code = Column(String(10), nullable=True)

    # Emergency Contact (PHI)
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    emergency_contact_relationship = Column(String(100), nullable=True)

    # Insurance (PHI)
    primary_insurance_plan_id = Column(String(255), nullable=True)

    # Preferences (OPERATIONAL)
    language = Column(String(10), default="en")
    communication_preferences = Column(JSONB, default=dict)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active")

    # Relationships
    appointments = relationship("AppointmentDB", back_populates="patient")


class AppointmentDB(Base):
    """SQLAlchemy model for Appointment."""
    __tablename__ = "appointments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    fhir_resource_id = Column(String(255), nullable=True)

    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    provider_id = Column(String(100), nullable=False)
    appointment_type = Column(String(50), nullable=False)
    appointment_type_display = Column(String(100), nullable=False)

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    timezone = Column(String(50), default="America/New_York")

    location = Column(String(200), nullable=True)
    visit_type = Column(String(20), default="in_person")

    status = Column(String(20), default="scheduled")

    # Scheduling metadata
    created_by = Column(String(100), default="system")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # No-show prediction
    no_show_risk = Column(Float, nullable=True)

    # Flags requiring HITL
    requires_hitl = Column(Boolean, default=False)
    hitl_reason = Column(String(500), nullable=True)

    # Patient linkage (PHI)
    patient_name = Column(String(200), nullable=True)

    # Relationships
    patient = relationship("PatientDB", back_populates="appointments")