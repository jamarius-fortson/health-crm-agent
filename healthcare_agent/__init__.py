"""
healthcare-crm-agent — HIPAA-compliant autonomous front-office and care-coordination platform.

This package implements a LangGraph-based multi-agent system for healthcare practice management,
operating strictly within a HIPAA compliance perimeter.

THREE LINES THIS SYSTEM NEVER CROSSES:
1. No clinical decision-making (diagnosis, treatment, medication, lab interpretation).
2. No PHI to non-BAA'd services (every LLM call through BAA-covered endpoints only).
3. No autonomous patient communication on clinical topics (routes to clinician immediately).
"""

__version__ = "0.1.0"
