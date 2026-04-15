"""
Red Flag Rules — Emergency Trigger Detection.

Hard-coded patterns that trigger IMMEDIATE human escalation.
These are non-negotiable: when detected, the agent stops all autonomous activity
for that patient and escalates to a human with the standard emergency message.

Red-flag patterns are versioned and must be reviewed by a clinical advisor.
This list is based on common emergency medical conditions that should never
be handled by an autonomous system.

Version: 1.0.0
Last reviewed: 2024-01-01 (requires clinical advisor sign-off)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RedFlagSeverity(str, Enum):
    """Severity levels for red-flag triggers."""
    CRITICAL = "critical"    # Immediate emergency — 911-level
    URGENT = "urgent"        # Same-day clinical attention needed
    ELEVATED = "elevated"    # Clinical review within 24 hours


class RedFlagCategory(str, Enum):
    """Categories of red-flag triggers."""
    CARDIAC = "cardiac"
    NEUROLOGICAL = "neurological"
    PSYCHIATRIC = "psychiatric"
    RESPIRATORY = "respiratory"
    TRAUMA = "trauma"
    OBSTETRIC = "obstetric"
    PEDIATRIC = "pediatric"
    ALLERGIC = "allergic"
    HEMORRHAGIC = "hemorrhagic"
    INGESTION = "ingestion"
    GENERAL_EMERGENCY = "general_emergency"


@dataclass(frozen=True)
class RedFlagRule:
    """A single red-flag rule."""
    rule_id: str
    name: str
    category: RedFlagCategory
    severity: RedFlagSeverity
    patterns: list[re.Pattern]
    auto_response: str
    clinical_note: str = ""


@dataclass(frozen=True)
class RedFlagTrigger:
    """Result of red-flag evaluation."""
    triggered: bool
    rule: RedFlagRule | None = None
    matched_text: str = ""
    timestamp: datetime | None = None


# ============================================================================
# STANDARD AUTO-RESPONSE MESSAGES
# These are the ONLY clinical-adjacent messages the system may send autonomously.
# They are hardcoded, non-negotiable, and never modified by LLMs.
# ============================================================================

CRITICAL_EMERGENCY_RESPONSE = (
    "Thank you for reaching out. Based on what you've described, "
    "we recommend you seek immediate medical attention. "
    "If this is a medical emergency, please call 911 or go to your nearest emergency room. "
    "We have notified our clinical team, who will follow up with you as soon as possible."
)

URGENT_CLINICAL_RESPONSE = (
    "Thank you for sharing this information. Our clinical team has been notified "
    "and will review your message promptly. If you need immediate medical attention, "
    "please call 911 or go to your nearest emergency room."
)

ELEVATED_CLINICAL_RESPONSE = (
    "Thank you for reaching out. We've flagged your message for clinical review "
    "and a member of our care team will contact you within 24 hours. "
    "If your symptoms worsen or you need urgent care, please call 911 or visit your nearest emergency room."
)


# ============================================================================
# RED FLAG RULES — Version 1.0.0
# ============================================================================

RED_FLAG_RULES: list[RedFlagRule] = [
    # --- CARDIAC ---
    RedFlagRule(
        rule_id="RF-001",
        name="Chest pain or pressure",
        category=RedFlagCategory.CARDIAC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:chest\s+pain|chest\s+pressure|chest\s+tightness|chest\s+hurts)\b", re.I),
            re.compile(r"\b(?:pain\s+in\s+(?:my\s+)?chest)\b", re.I),
            re.compile(r"\b(?:heart\s+(?:attack|palpitations|racing|fluttering))\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible acute coronary syndrome — requires immediate evaluation",
    ),

    # --- NEUROLOGICAL ---
    RedFlagRule(
        rule_id="RF-002",
        name="Stroke symptoms (FAST)",
        category=RedFlagCategory.NEUROLOGICAL,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:face\s+droop|facial\s+droop|one\s+side\s+of\s+my\s+face)\b", re.I),
            re.compile(r"\b(?:arm\s+weakness|can'?t\s+raise\s+my\s+arm|arm\s+numbness)\b", re.I),
            re.compile(r"\b(?:slurred\s+speech|can'?t\s+speak|difficulty\s+speaking|speech\s+problem)\b", re.I),
            re.compile(r"\b(?:sudden\s+(?:severe\s+)?headache|worst\s+headache\s+(?:of\s+my\s+life|ever))\b", re.I),
            re.compile(r"\b(?:stroke)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible stroke — requires immediate evaluation (time-sensitive for tPA)",
    ),

    # --- NEUROLOGICAL: Seizure/LOC ---
    RedFlagRule(
        rule_id="RF-003",
        name="Seizure or loss of consciousness",
        category=RedFlagCategory.NEUROLOGICAL,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:seizure|convulsions|shaking\s+uncontrollably)\b", re.I),
            re.compile(r"\b(?:passed\s+out|lost\s+consciousness|fainted|black\s+out)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible seizure or syncope — requires immediate evaluation",
    ),

    # --- PSYCHIATRIC ---
    RedFlagRule(
        rule_id="RF-004",
        name="Suicidal ideation",
        category=RedFlagCategory.PSYCHIATRIC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:suicid|want\s+to\s+die|kill\s+myself|don'?t\s+want\s+to\s+live)\b", re.I),
            re.compile(r"\b(?:end\s+my\s+life|harm\s+myself|self.harm|cutting\s+myself)\b", re.I),
            re.compile(r"\b(?:feel\s+like\s+i\s+can'?t\s+go\s+on|no\s+reason\s+to\s+live)\b", re.I),
        ],
        auto_response=(
            "Thank you for reaching out. You are not alone. If you are in crisis, "
            "please call or text 988 (Suicide & Crisis Lifeline) or call 911. "
            "Our clinical team has been notified and will reach out to you as soon as possible. "
            "You can also text HOME to 741741 to reach the Crisis Text Line."
        ),
        clinical_note="Active suicidal ideation — requires immediate crisis intervention",
    ),

    # --- RESPIRATORY ---
    RedFlagRule(
        rule_id="RF-005",
        name="Severe breathing difficulty",
        category=RedFlagCategory.RESPIRATORY,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:can'?t\s+breathe|cannot\s+breathe|unable\s+to\s+breathe)\b", re.I),
            re.compile(r"\b(?:severe\s+shortness\s+of\s+breath|severe\s+difficulty\s+breathe)\b", re.I),
            re.compile(r"\b(?:lips\s+turning\s+blue|turning\s+blue)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible respiratory failure — requires immediate evaluation",
    ),

    # --- ALLERGIC ---
    RedFlagRule(
        rule_id="RF-006",
        name="Severe allergic reaction / Anaphylaxis",
        category=RedFlagCategory.ALLERGIC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:throat\s+closing|throat\s+swelling|tongue\s+swelling)\b", re.I),
            re.compile(r"\b(?:anaphylax|severe\s+allergic\s+reaction)\b", re.I),
            re.compile(r"\b(?:trouble\s+swallowing\s+and\s+hives)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible anaphylaxis — requires immediate epinephrine and evaluation",
    ),

    # --- HEMORRHAGIC ---
    RedFlagRule(
        rule_id="RF-007",
        name="Severe bleeding",
        category=RedFlagCategory.HEMORRHAGIC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:severe\s+bleeding|can'?t\s+stop\s+bleeding|bleeding\s+won'?t\s+stop)\b", re.I),
            re.compile(r"\b(?:coughing\s+up\s+blood|vomiting\s+blood|blood\s+in\s+vomit)\b", re.I),
            re.compile(r"\b(?:black\s+tarry\s+stool|blood\s+in\s+stool)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Severe hemorrhage — requires immediate evaluation",
    ),

    # --- OBSTETRIC ---
    RedFlagRule(
        rule_id="RF-008",
        name="Pregnancy emergency",
        category=RedFlagCategory.OBSTETRIC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:pregnant\s+and\s+bleeding|vaginal\s+bleeding\s+and\s+pregnant)\b", re.I),
            re.compile(r"\b(?:pregnancy\s+bleeding|bleeding\s+during\s+pregnancy)\b", re.I),
            re.compile(r"\b(?:severe\s+abdominal\s+pain\s+and\s+pregnant)\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Possible obstetric emergency — requires immediate evaluation",
    ),

    # --- PEDIATRIC ---
    RedFlagRule(
        rule_id="RF-009",
        name="Child emergency",
        category=RedFlagCategory.PEDIATRIC,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:my\s+(?:baby|infant|child)\s+(?:won'?t\s+wake|is\s+unresponsive|won'?t\s+eat))\b", re.I),
            re.compile(r"\b(?:baby\s+turning\s+blue|infant\s+turning\s+blue|child\s+turning\s+blue)\b", re.I),
            re.compile(r"\b(?:child\s+fever\s+(?:10[4-9]|1[0-9]{2}|[45]0))\b", re.I),
            re.compile(r"\b(?:child\s+(?:fell|hit\s+head)\s+and\s+(?:vomiting|unconscious|not\s+acting\s+normal))\b", re.I),
        ],
        auto_response=CRITICAL_EMERGENCY_RESPONSE,
        clinical_note="Pediatric emergency — requires immediate evaluation",
    ),

    # --- INGESTION ---
    RedFlagRule(
        rule_id="RF-010",
        name="Poisoning / Overdose",
        category=RedFlagCategory.INGESTION,
        severity=RedFlagSeverity.CRITICAL,
        patterns=[
            re.compile(r"\b(?:overdose|took\s+too\s+many|took\s+too\s+much)\b", re.I),
            re.compile(r"\b(?:poison|swallowed\s+poison|drank\s+(?:bleach|cleaner))\b", re.I),
            re.compile(r"\b(?:poison\s+control)\b", re.I),
        ],
        auto_response=(
            "This is a medical emergency. Please call 911 or the Poison Control Center "
            "at 1-800-222-1222 immediately. Our clinical team has also been notified."
        ),
        clinical_note="Possible poisoning or overdose — requires immediate evaluation",
    ),

    # --- GENERAL: Child injury ---
    RedFlagRule(
        rule_id="RF-011",
        name="Child injury",
        category=RedFlagCategory.PEDIATRIC,
        severity=RedFlagSeverity.URGENT,
        patterns=[
            re.compile(r"\b(?:my\s+child\s+(?:fell|hit|injured|burned|cut))\b", re.I),
            re.compile(r"\b(?:baby\s+(?:fell|hit\s+head|injured))\b", re.I),
        ],
        auto_response=URGENT_CLINICAL_RESPONSE,
        clinical_note="Child injury — requires prompt clinical assessment",
    ),

    # --- GENERAL: Worsening symptoms ---
    RedFlagRule(
        rule_id="RF-012",
        name="Rapidly worsening condition",
        category=RedFlagCategory.GENERAL_EMERGENCY,
        severity=RedFlagSeverity.URGENT,
        patterns=[
            re.compile(r"\b(?:rapidly\s+(?:getting\s+)?worse|suddenly\s+much\s+worse)\b", re.I),
            re.compile(r"\b(?:much\s+worse\s+than\s+(?:before|yesterday|last\s+week))\b", re.I),
        ],
        auto_response=URGENT_CLINICAL_RESPONSE,
        clinical_note="Rapid clinical deterioration — requires prompt assessment",
    ),
]


def check_red_flags(text: str) -> RedFlagTrigger:
    """
    Check text against all red-flag rules.

    Returns the HIGHEST-severity trigger if any rule matches.
    CRITICAL > URGENT > ELEVATED
    """
    from datetime import datetime as _dt

    # Sort rules by severity (CRITICAL first)
    severity_order = {
        RedFlagSeverity.CRITICAL: 0,
        RedFlagSeverity.URGENT: 1,
        RedFlagSeverity.ELEVATED: 2,
    }
    sorted_rules = sorted(RED_FLAG_RULES, key=lambda r: severity_order[r.severity])

    for rule in sorted_rules:
        for pattern in rule.patterns:
            match = pattern.search(text)
            if match:
                return RedFlagTrigger(
                    triggered=True,
                    rule=rule,
                    matched_text=match.group(0),
                    timestamp=_dt.utcnow(),
                )

    return RedFlagTrigger(triggered=False)


def get_red_flag_auto_response(trigger: RedFlagTrigger) -> str:
    """Get the standard auto-response for a red-flag trigger."""
    if not trigger.triggered or trigger.rule is None:
        return ""
    return trigger.rule.auto_response
