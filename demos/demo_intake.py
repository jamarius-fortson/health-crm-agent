import asyncio
from healthcare_agent.graph.supervisor import get_supervisor

async def run_intake_demo():
    print("--- Starting Intake Agent Demo (Normal Workflow) ---")
    supervisor = get_supervisor()
    
    initial_state = {
        "event_type": "intake_form_submitted",
        "event_data": {
            "patient_id": "synthea-maria-garcia",
            "chief_complaint": "Annual physical and renewal of blood pressure medication.",
            "medications": ["Lisinopril 10mg"],
            "allergies": ["Penicillin"],
            "history_flags": ["hypertension"]
        },
        "agent_results": {},
        "hitl_queue": [],
        "audit_entry_ids": [],
    }
    
    result = await supervisor.invoke(initial_state)
    intake_res = result.get("agent_results", {}).get("intake", {})
    print(f"Intake Status: {intake_res.get('status')}")
    print(f"Summary ID: {intake_res.get('summary_id')}")
    print(f"Next Node: {result.get('next_node')}\n")

    print("--- Starting Intake Agent Demo (Red Flag Workflow) ---")
    red_flag_state = {
        "event_type": "intake_form_submitted",
        "event_data": {
            "patient_id": "test-red-flag",
            "chief_complaint": "I've been having intense chest pain and shortness of breath for the last hour.",
        },
        "agent_results": {},
        "hitl_queue": [],
        "audit_entry_ids": [],
    }
    
    result_rf = await supervisor.invoke(red_flag_state)
    intake_rf = result_rf.get("agent_results", {}).get("intake", {})
    print(f"Intake Status: {intake_rf.get('status')}")
    print(f"Red Flag Triggered: {intake_rf.get('red_flag_triggered')}")
    print(f"Reason: {intake_rf.get('reason')}")
    print(f"Next Node: {result_rf.get('next_node')}")
    print(f"HITL Queue Depth: {len(result_rf.get('hitl_queue', []))}")
    if result_rf.get('hitl_queue'):
        print(f"HITL Action: {result_rf['hitl_queue'][0].get('action_type')}")

if __name__ == "__main__":
    asyncio.run(run_intake_demo())
