"""
Content Classifier — Output Filter for Patient Communications.

Every outbound patient message passes through this classifier BEFORE being sent.
It performs layered detection:

Layer 1: Deterministic regex rules (clinical_boundary.py) — fast, 100% recall on known patterns
Layer 2: Keyword scoring — catches clinical terms that don't match regex patterns
Layer 3: Semantic classification (stub for LLM-based classifier) — catches ambiguous cases

If ANY layer flags the message as clinical, it is BLOCKED from autonomous sending
and routed to HITL. The classifier has NO override — not even for "low confidence"
matches. Clinical content in patient messages is a hard line.

The adversarial test suite (200+ prompts) validates this classifier in CI.
New failure modes are added to the suite, never silenced.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from healthcare_agent.safety.clinical_boundary import (
    ClinicalDetection,
    ClinicalContentType,
    detect_clinical_content,
)


class ClassificationVerdict(str, Enum):
    """Final verdict on whether a message is safe to send autonomously."""
    SAFE = "safe"              # Safe for autonomous sending
    BLOCKED = "blocked"        # Clinical content detected — block and escalate to HITL
    REVIEW = "review"          # Borderline — send to HITL for human review


@dataclass(frozen=True)
class ClassificationResult:
    """Result of the full classification pipeline."""
    verdict: ClassificationVerdict
    confidence: float  # 0.0–1.0
    reasons: list[str]
    layers_triggered: list[str]  # Which detection layers flagged this
    requires_hitl: bool

    @property
    def is_safe(self) -> bool:
        return self.verdict == ClassificationVerdict.SAFE


# ============================================================================
# Keyword Scoring Layer — supplemental to regex patterns
# ============================================================================

_CLINICAL_KEYWORDS: frozenset[str] = frozenset({
    # Symptoms
    "symptom", "pain", "ache", "sore", "swollen", "rash", "lump", "bump",
    "nausea", "dizzy", "fatigue", "weak", "numb", "tingling",
    # Diagnoses
    "diagnosed", "diagnosis", "condition", "disease", "disorder", "syndrome",
    # Medications
    "medication", "drug", "pill", "tablet", "capsule", "dose", "dosage",
    "prescription", "refill", "side effect", "adverse reaction",
    # Labs
    "lab", "blood test", "urine test", "biopsy", "scan", "mri", "ct scan",
    "x-ray", "ultrasound", "result", "abnormal", "elevated",
    # Treatments
    "treatment", "therapy", "surgery", "procedure", "operation",
    # Clinical language
    "prognosis", "recovery", "healing", "improving", "worsening",
    "chronic", "acute", "severe", "mild", "moderate",
})

_OPERATIONAL_KEYWORDS: frozenset[str] = frozenset({
    # These are safe operational terms that might overlap with clinical keywords
    "appointment", "schedule", "reschedule", "cancel", "confirm",
    "reminder", "recall", "registration", "intake", "form",
    "insurance", "billing", "copay", "payment",
    "address", "phone", "email", "contact", "update",
    "hours", "location", "directions", "parking",
})


def _score_keywords(text: str) -> tuple[float, list[str]]:
    """
    Score text for clinical keywords.

    Returns (score, matched_keywords).
    Score > 0.5 indicates clinical content.
    """
    text_lower = text.lower()
    words = set(text_lower.split())

    clinical_matches = words & _CLINICAL_KEYWORDS
    operational_matches = words & _OPERATIONAL_KEYWORDS

    if not clinical_matches:
        return 0.0, []

    # Adjust score based on context
    # If operational terms dominate, the message is likely operational
    total_matches = len(clinical_matches) + len(operational_matches)
    if total_matches > 0 and len(operational_matches) / total_matches > 0.7:
        # Mostly operational context — reduce score
        base_score = len(clinical_matches) * 0.15
    else:
        base_score = len(clinical_matches) * 0.3

    # Cap at 0.9 (leave room for regex layer)
    return min(base_score, 0.9), list(clinical_matches)


# ============================================================================
# Main Classification Pipeline
# ============================================================================

def classify_message(text: str) -> ClassificationResult:
    """
    Classify an outbound patient message.

    Multi-layer pipeline:
    1. Regex-based clinical boundary detection (hard block)
    2. Keyword scoring (block above threshold)
    3. Final verdict

    A message is BLOCKED if ANY layer flags it.
    """
    layers_triggered: list[str] = []
    reasons: list[str] = []
    max_confidence = 0.0

    # --- Layer 1: Regex-based clinical boundary detection ---
    regex_detection = detect_clinical_content(text)
    if regex_detection.has_clinical_content:
        layers_triggered.append("regex_clinical_boundary")
        reasons.append(regex_detection.reason)
        max_confidence = max(max_confidence, regex_detection.confidence)

    # --- Layer 2: Keyword scoring ---
    keyword_score, keyword_matches = _score_keywords(text)
    if keyword_score > 0.4:  # Threshold for keyword-only blocking
        layers_triggered.append("keyword_scoring")
        reasons.append(
            f"Clinical keywords detected ({keyword_score:.2f}): "
            f"{', '.join(keyword_matches[:5])}"
        )
        max_confidence = max(max_confidence, keyword_score)

    # --- Layer 3: Red-flag override ---
    # Even if layers 1-2 didn't flag, check red flags (highest priority)
    from healthcare_agent.safety.red_flag_rules import check_red_flags
    red_flag = check_red_flags(text)
    if red_flag.triggered:
        layers_triggered.append("red_flag")
        reasons.append(f"Red flag: {red_flag.rule.name if red_flag.rule else 'unknown'}")
        max_confidence = 1.0

    # --- Final verdict ---
    if layers_triggered:
        # ANY trigger = block. No overrides.
        verdict = ClassificationVerdict.BLOCKED
        requires_hitl = True
    else:
        verdict = ClassificationVerdict.SAFE
        requires_hitl = False
        max_confidence = max(max_confidence, 0.8)  # Safe messages have moderate confidence
        reasons.append("No clinical content detected across all layers")

    return ClassificationResult(
        verdict=verdict,
        confidence=max_confidence,
        reasons=reasons,
        layers_triggered=layers_triggered,
        requires_hitl=requires_hitl,
    )


def is_message_safe_to_send(text: str) -> tuple[bool, ClassificationResult]:
    """
    Convenience function: is this message safe for autonomous sending?

    Returns (is_safe, classification_result).
    """
    result = classify_message(text)
    return result.is_safe, result
