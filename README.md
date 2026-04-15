# Healthcare CRM Agent

HIPAA-compliant autonomous front-office and care-coordination platform for small-to-mid healthcare practices.

## Description

This project provides an autonomous agent system for healthcare practices, handling scheduling, compliance, safety, and integrations with various healthcare standards.

## Installation

1. Install Python 3.11+
2. Install dependencies: `pip install -e .`
3. Run the application: `uvicorn healthcare_agent.api.app:app --host 0.0.0.0 --port 8000`

## Features

- Scheduling agents
- Compliance and audit
- PHI protection
- FHIR and HL7 integrations
- FastAPI backend

## License

Apache-2.0