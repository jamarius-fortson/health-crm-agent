"""
Clinical Boundary Detector.

Detects clinical content in ANY input or output text — patient messages, agent responses,
LLM outputs, intake forms, etc.

This is a defense-in-depth layer:
1. Regex rules catch known clinical terms (fast, deterministic)
2. Keyword lists catch symptom/medication/diagnosis language
3. A higher-level classifier (content_classifier.py) does semantic analysis

If clinical content is detected, the message is BLOCKED from autonomous sending
and routed to HITL.

HARD LINE: This system NEVER generates clinical advice. The detector catches
both accidental and adversarial clinical content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ClinicalContentType(str, Enum):
    """Categories of clinical content that must be blocked from autonomous output."""
    SYMPTOM = "symptom"
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"
    DOSAGE = "dosage"
    TREATMENT = "treatment"
    LAB_RESULT = "lab_result"
    MEDICAL_ADVICE = "medical_advice"
    TRIAGE = "triage"
    PROCEDURE_RECOMMENDATION = "procedure_recommendation"
    PROGNOSIS = "prognosis"


@dataclass(frozen=True)
class ClinicalDetection:
    """Result of clinical content detection."""
    has_clinical_content: bool
    detected_types: list[ClinicalContentType]
    confidence: float  # 0.0–1.0
    matched_terms: list[str]
    requires_hitl: bool
    reason: str = ""


# ============================================================================
# Clinical Term Patterns — curated, versioned, clinically reviewed
# ============================================================================

# Symptom keywords — phrases patients use to describe symptoms
_SYMPTOM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:chest\s+pain|chest\s+tightness|chest\s+pressure)\b", re.I), "chest pain/tightness/pressure"),
    (re.compile(r"\b(?:shortness\s+of\s+breath|can'?t\s+breathe|difficulty\s+breathe|trouble\s+breathe)\b", re.I), "shortness of breath"),
    (re.compile(r"\b(?:severe\s+headache|worst\s+headache)\b", re.I), "severe headache"),
    (re.compile(r"\b(?:suicid|want\s+to\s+die|kill\s+myself|don'?t\s+want\s+to\s+live|harm\s+myself|self.harm)\b", re.I), "suicidal ideation"),
    (re.compile(r"\b(?:stroke|face\s+drooping|arm\s+weakness|speech\s+difficulty|fas?t)\b", re.I), "stroke symptoms"),
    (re.compile(r"\b(?:bleeding|hemorrhage|blood\s+in)\b", re.I), "bleeding"),
    (re.compile(r"\b(?:fever|high\s+temperature|temp\s+of)\b", re.I), "fever"),
    (re.compile(r"\b(?:rash|hives|itching|swelling)\b", re.I), "rash/swelling"),
    (re.compile(r"\b(?:nausea|vomiting|throwing\s+up)\b", re.I), "nausea/vomiting"),
    (re.compile(r"\b(?:dizzy|dizziness|lightheaded|fainting)\b", re.I), "dizziness/fainting"),
    (re.compile(r"\b(?:numb|tingling|weakness)\b", re.I), "numbness/weakness"),
    (re.compile(r"\b(?:abdominal\s+pain|stomach\s+pain|belly\s+pain)\b", re.I), "abdominal pain"),
    (re.compile(r"\b(?:back\s+pain|neck\s+pain|joint\s+pain)\b", re.I), "pain"),
    (re.compile(r"\b(?:cough|sore\s+throat|runny\s+nose|congestion)\b", re.I), "respiratory symptoms"),
    (re.compile(r"\b(?:painful\s+urination|blood\s+in\s+urine|frequent\s+urination)\b", re.I), "urinary symptoms"),
    (re.compile(r"\b(?:blurred\s+vision|vision\s+change|eye\s+pain)\b", re.I), "vision symptoms"),
    (re.compile(r"\b(?:pregnancy|pregnant|vaginal\s+bleeding|contraction)\b", re.I), "pregnancy-related"),
    (re.compile(r"\b(?:seizure|convulsion|passing\s+out)\b", re.I), "seizure/loss of consciousness"),
    (re.compile(r"\b(?:allergic\s+reaction|anaphylax|throat\s+closing)\b", re.I), "allergic reaction"),
    (re.compile(r"\b(?:hurt|pain|sore|aching|throbbing|burning\s+sensation)\b", re.I), "pain descriptors"),
]

# Diagnosis keywords — NEVER let the system discuss diagnoses autonomously
_DIAGNOSIS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:diabetes|diabetic)\b", re.I), "diabetes"),
    (re.compile(r"\b(?:hypertension|high\s+blood\s+pressure)\b", re.I), "hypertension"),
    (re.compile(r"\b(?:cancer|tumor|malignant|carcinoma)\b", re.I), "cancer"),
    (re.compile(r"\b(?:depression|anxiety|bipolar|schizophrenia|ptsd|adhd)\b", re.I), "mental health diagnosis"),
    (re.compile(r"\b(?:asthma|copd|emphysema|bronchitis)\b", re.I), "respiratory diagnosis"),
    (re.compile(r"\b(?:arthritis|osteoporosis|fibromyalgia)\b", re.I), "musculoskeletal diagnosis"),
    (re.compile(r"\b(?:infection|bacterial|viral|fungal|sepsis)\b", re.I), "infection"),
    (re.compile(r"\b(?:heart\s+(?:attack|failure|disease)|cardiac|arrhythmia)\b", re.I), "cardiac diagnosis"),
    (re.compile(r"\b(?:icd|icd-?10|diagnosis\s+code|dx\s+code)\b", re.I), "diagnosis codes"),
    (re.compile(r"\b(?:you\s+have|you\s+may\s+have|it\s+looks\s+like|this\s+suggests)\b.*(?:condition|disease|disorder)", re.I), "diagnostic language"),
]

# Medication names and related terms
_MEDICATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:lisinopril|metformin|amlodipine|atorvastatin|omeprazole|levothyroxine|albuterol|metoprolol|gabapentin|hydrochlorothiazide)\b", re.I), "common medication"),
    (re.compile(r"\b(?:ibuprofen|acetaminophen|aspirin|naproxen|diclofenac)\b", re.I), "pain medication"),
    (re.compile(r"\b(?:amoxicillin|azithromycin|ciprofloxacin|doxycycline|cephalexin)\b", re.I), "antibiotic"),
    (re.compile(r"\b(?:insulin|metformin|glipizide|glyburide)\b", re.I), "diabetes medication"),
    (re.compile(r"\b(?:sertraline|fluoxetine|escitalopram|venlafaxine|bupropion)\b", re.I), "psychiatric medication"),
    (re.compile(r"\b(?:prednisone|steroid|corticosteroid)\b", re.I), "steroid"),
    (re.compile(r"\b(?:mg|milligram|mcg|microgram|ml|milliliter|units?\s+of)\b", re.I), "dosage unit"),
    (re.compile(r"\b(?:take\s+\d+|dose|dosage|prescription|refill|medication)\b", re.I), "medication instruction"),
    (re.compile(r"\b(?:twice\s+daily|three\s+times|once\s+daily|as\s+needed|prn|bid|tid|qd)\b", re.I), "dosage frequency"),
]

# Treatment language — NEVER autonomous
_TREATMENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:you\s+should\s+treat|treatment|therapy|surgery|procedure|operation)\b", re.I), "treatment"),
    (re.compile(r"\b(?:i\s+recommend|you\s+need|you\s+should|try\s+taking)\b", re.I), "recommendation language"),
    (re.compile(r"\b(?:physical\s+therapy|occupational\s+therapy|speech\s+therapy)\b", re.I), "therapy type"),
    (re.compile(r"\b(?:radiation|chemotherapy|immunotherapy)\b", re.I), "cancer treatment"),
]

# Lab result language
_LAB_RESULT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:lab\s+result|blood\s+test|test\s+result|a1c|hemoglobin|cholesterol)\b", re.I), "lab result"),
    (re.compile(r"\b(?:your\s+(?:result|labs|levels?)|results\s+show|labs\s+show)\b", re.I), "result discussion"),
    (re.compile(r"\b(?:normal|abnormal|high|low|elevated|borderline)\b.*(?:level|count|result)", re.I), "result interpretation"),
]

# Medical advice patterns — the system should NEVER generate these
_MEDICAL_ADVICE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:you\s+should\s+go\s+to\s+the\s+er|go\s+to\s+emergency|call\s+911|seek\s+immediate)\b", re.I), "emergency advice"),
    (re.compile(r"\b(?:it'?s\s+(?:serious|urgent|not\s+serious|nothing\s+to\s+worry))\b", re.I), "urgency assessment"),
    (re.compile(r"\b(?:based\s+on\s+your\s+symptoms|given\s+your\s+symptoms)\b", re.I), "symptom-based assessment"),
    (re.compile(r"\b(?:this\s+(?:is|sounds)\s+(?:likely|probably|could\s+be))\b", re.I), "diagnostic speculation"),
]


def detect_clinical_content(text: str) -> ClinicalDetection:
    """
    Scan text for clinical content.

    Returns a detection result with all matched categories and terms.
    If has_clinical_content is True, the text MUST NOT be sent autonomously.
    """
    detected: dict[ClinicalContentType, list[str]] = {
        ClinicalContentType.SYMPTOM: [],
        ClinicalContentType.DIAGNOSIS: [],
        ClinicalContentType.MEDICATION: [],
        ClinicalContentType.DOSAGE: [],
        ClinicalContentType.TREATMENT: [],
        ClinicalContentType.LAB_RESULT: [],
        ClinicalContentType.MEDICAL_ADVICE: [],
    }

    all_matched_terms: list[str] = []

    # Check symptom patterns
    for pattern, term in _SYMPTOM_PATTERNS:
        if pattern.search(text):
            detected[ClinicalContentType.SYMPTOM].append(term)
            all_matched_terms.append(term)

    # Check diagnosis patterns
    for pattern, term in _DIAGNOSIS_PATTERNS:
        if pattern.search(text):
            detected[ClinicalContentType.DIAGNOSIS].append(term)
            all_matched_terms.append(term)

    # Check medication patterns
    for pattern, term in _MEDICATION_PATTERNS:
        if pattern.search(text):
            if any(kw in term.lower() for kw in ["dosage", "unit", "frequency", "instruction"]):
                detected[ClinicalContentType.DOSAGE].append(term)
            elif any(kw in term.lower() for kw in ["medication", "antibiotic", "diabetes", "psychiatric", "steroid", "pain medication", "common medication"]):
                detected[ClinicalContentType.MEDICATION].append(term)
            all_matched_terms.append(term)

    # Check treatment patterns
    for pattern, term in _TREATMENT_PATTERNS:
        if pattern.search(text):
            detected[ClinicalContentType.TREATMENT].append(term)
            all_matched_terms.append(term)

    # Check lab result patterns
    for pattern, term in _LAB_RESULT_PATTERNS:
        if pattern.search(text):
            detected[ClinicalContentType.LAB_RESULT].append(term)
            all_matched_terms.append(term)

    # Check medical advice patterns
    for pattern, term in _MEDICAL_ADVICE_PATTERNS:
        if pattern.search(text):
            detected[ClinicalContentType.MEDICAL_ADVICE].append(term)
            all_matched_terms.append(term)

    # Build result
    has_clinical = len(all_matched_terms) > 0
    detected_types = [t for t, terms in detected.items() if terms]

    # Confidence based on number and type of matches
    if len(all_matched_terms) >= 3:
        confidence = 0.99
    elif len(all_matched_terms) >= 2:
        confidence = 0.95
    elif len(all_matched_terms) >= 1:
        # Check severity of matched types
        if ClinicalContentType.MEDICAL_ADVICE in detected_types:
            confidence = 0.95
        elif ClinicalContentType.SYMPTOM in detected_types:
            confidence = 0.85
        else:
            confidence = 0.80
    else:
        confidence = 0.0

    # Calculate reason
    if has_clinical:
        type_names = ", ".join(t.value for t in detected_types)
        reason = f"Clinical content detected: {type_names}. Matched terms: {', '.join(all_matched_terms[:5])}"
    else:
        reason = "No clinical content detected"

    return ClinicalDetection(
        has_clinical_content=has_clinical,
        detected_types=detected_types,
        confidence=confidence,
        matched_terms=all_matched_terms,
        requires_hitl=has_clinical,
        reason=reason,
    )


def is_clinically_safe(text: str) -> bool:
    """
    Quick check: is this text safe for autonomous sending?

    Returns True if no clinical content detected.
    """
    return not detect_clinical_content(text).has_clinical_content
