import asyncio
from datetime import datetime, timedelta
from healthcare_agent.graph.supervisor import get_supervisor
from healthcare_agent.graph.router import SCHEDULING_AGENT
from healthcare_agent.models.domain import AppointmentType

async def run_demo():
    print("Starting Scheduling Agent Demo...")
    supervisor = get_supervisor()
    
    # Mock clinic config and patient
    tomorrow = datetime.utcnow() + timedelta(days=1, hours=10)
    
    initial_state = {
        "patient_id": "test-patient-123",
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "fhir_resource_id": "patient-123",
            "phone": "555-0199"
        },
        "current_task": "schedule_appointment",
        "event_type": "schedule_appointment",
        "clinic_config": {
            "providers": {
                "dr-smith": {"blocked_times": []}
            },
            "appointment_types": {
                "follow_up": {"display_name": "Follow-Up Visit", "duration_minutes": 15}
            },
            "scheduling_rules": {"max_cancellations_before_hitl": 3}
        },
        "task_context": {
            "provider_id": "dr-smith",
            "appointment_type": "follow_up",
            "requested_time": tomorrow.isoformat(),
        },
        "agent_results": {},
        "hitl_queue": [],
        "audit_entry_ids": [],
    }
    
    print(f"Invoking graph for task: {initial_state['current_task']}")
    result = await supervisor.invoke(initial_state)
    
    import json
    # Use a custom encoder for datetime if needed, or just print the dict
    print("Full Context Result Keys:", list(result.keys()))
    
    sched_res = result.get("agent_results", {}).get("scheduling", {})
    print(f"Scheduling Status: {sched_res.get('status')}")
    
    if sched_res.get("status") == "scheduled":
        appt = sched_res.get("appointment", {})
        print(f"Appointment ID: {appt.get('id')}")
        print(f"FHIR ID: {appt.get('fhir_resource_id')}")
        print(f"Start: {appt.get('start_time')}")
        print(f"Next Node: {result.get('next_node')}")
    else:
        print(f"Error: {sched_res.get('error')}")

if __name__ == "__main__":
    asyncio.run(run_demo())
