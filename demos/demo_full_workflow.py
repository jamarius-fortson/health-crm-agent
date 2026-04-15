import asyncio
from healthcare_agent.graph.supervisor import get_supervisor

async def run_end_to_end_demo():
    print("--- Starting End-to-End Demo (Intake -> Insurance -> Scheduling -> Comms) ---")
    supervisor = get_supervisor()
    
    initial_state = {
        "event_type": "intake_form_submitted",
        "patient_id": "maria-garcia-001",
        "event_data": {
            "patient_id": "maria-garcia-001",
            "first_name": "Maria",
            "last_name": "Garcia",
            "date_of_birth": "1985-03-15",
            "phone": "555-0101",
            "email": "maria@example.com",
            "chief_complaint": "Annual checkup",
            "payer_id": "AETNA",
            "subscriber_id": "A12345678"
        },
        "agent_results": {},
        "hitl_queue": [],
        "audit_entry_ids": [],
        "clinic_config": {
            "providers": {"dr-smith": {"blocked_times": []}},
            "appointment_types": {"follow_up": {"display_name": "Follow-Up", "duration_minutes": 15}},
            "scheduling_rules": {"max_cancellations_before_hitl": 3}
        },
        "task_context": {
            "provider_id": "dr-smith",
            "appointment_type": "follow_up",
            "requested_time": "2026-04-20T10:00:00"
        }
    }
    
    print("Invoking graph...")
    result = await supervisor.invoke(initial_state)
    
    agent_results = result.get("agent_results", {})
    
    print("\n--- Phase 4: Intake ---")
    intake = agent_results.get("intake", {})
    print(f"Status: {intake.get('status')}")
    
    print("\n--- Phase 5: Insurance ---")
    insurance = agent_results.get("insurance", {})
    print(f"Status: {insurance.get('status')}")
    print(f"Payer: {insurance.get('payer_name')}")
    print(f"Eligibility: {insurance.get('eligibility_status')}")
    
    print("\n--- Phase 3: Scheduling ---")
    scheduling = agent_results.get("scheduling", {})
    print(f"Status: {scheduling.get('status')}")
    if scheduling.get("appointment"):
        print(f"Appointment ID: {scheduling['appointment']['id']}")
        print(f"EHR ID: {scheduling['appointment']['fhir_resource_id']}")
    
    print("\n--- Phase 6: Communications ---")
    communications = agent_results.get("communications", {})
    print(f"Status: {communications.get('status')}")
    print(f"Channel: {communications.get('channel')}")
    print(f"Message: {communications.get('message_body')}")
    
    print(f"\nWorkflow Terminal: {result.get('terminal')}")
    print(f"Final Path: {list(agent_results.keys())}")

if __name__ == "__main__":
    asyncio.run(run_end_to_end_demo())
