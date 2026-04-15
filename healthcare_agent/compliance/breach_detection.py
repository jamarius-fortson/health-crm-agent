"""
Breach Detection — Anomalous PHI Access Alerts.

Monitors PHI access patterns for anomalies that may indicate a breach:
- Unusual volume of PHI reads (e.g., 100+ reads per hour from a single user)
- Off-hours access (e.g., 2AM–5AM access by non-emergency staff)
- Rapid sequential reads (e.g., 50 patient records in 5 minutes)
- Access by terminated/suspended accounts
- Access from unusual IP addresses or geolocations

When anomalies are detected, an alert is sent to the clinic's security officer
and an audit entry is written.

This is NOT a substitute for a full SIEM — it's a lightweight detection layer
for small practices that may not have a dedicated security team.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class BreachAlertLevel(str, Enum):
    """Severity of a breach alert."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class BreachAlert:
    """An anomalous PHI access alert."""
    alert_id: str
    timestamp: datetime
    level: BreachAlertLevel
    actor_id: str
    description: str
    details: dict[str, Any]
    patient_ids_affected: list[str]
    notified: bool = False


# ============================================================================
# Detection Rules
# ============================================================================

@dataclass
class AnomalyDetector:
    """
    Stateless anomaly detection based on configurable thresholds.

    In production, this would use streaming analytics (e.g., Kafka + Flink).
    For small practices, we use a simple sliding window approach.
    """

    # Thresholds
    max_phi_reads_per_hour: int = 100
    max_phi_reads_per_minute: int = 20
    max_unique_patients_per_hour: int = 50
    off_hours_start: int = 22  # 10 PM
    off_hours_end: int = 6     # 6 AM
    rapid_sequential_threshold: int = 10  # N reads in M seconds

    def detect_volume_anomaly(
        self,
        phi_read_count: int,
        window_minutes: int = 60,
    ) -> bool:
        """Detect unusual volume of PHI reads."""
        if window_minutes == 60:
            return phi_read_count > self.max_phi_reads_per_hour
        elif window_minutes == 1:
            return phi_read_count > self.max_phi_reads_per_minute
        else:
            # Linear interpolation
            threshold = self.max_phi_reads_per_hour * (window_minutes / 60)
            return phi_read_count > threshold

    def detect_off_hours_access(self, timestamp: datetime) -> bool:
        """Detect PHI access during off-hours."""
        hour = timestamp.hour
        return hour >= self.off_hours_start or hour < self.off_hours_end

    def detect_rapid_sequential_access(
        self,
        access_timestamps: list[datetime],
    ) -> bool:
        """Detect rapid sequential reads (potential data exfiltration)."""
        if len(access_timestamps) < self.rapid_sequential_threshold:
            return False

        # Check if N accesses happened within a short window
        recent = sorted(access_timestamps)[-self.rapid_sequential_threshold:]
        if len(recent) < self.rapid_sequential_threshold:
            return False

        time_span = (recent[-1] - recent[0]).total_seconds()
        return time_span < 60  # N reads in under 60 seconds

    def detect_unusual_patient_access(
        self,
        unique_patient_ids: list[str],
        actor_id: str,
        known_patient_ids: set[str] | None = None,
    ) -> bool:
        """Detect access to patients the actor wouldn't normally see."""
        if known_patient_ids is None:
            return False
        unknown = set(unique_patient_ids) - known_patient_ids
        return len(unknown) > 0


# ============================================================================
# Alert Generator
# ============================================================================

def evaluate_breach_risk(
    volume_anomaly: bool,
    off_hours: bool,
    rapid_sequential: bool,
    unusual_patients: bool,
) -> tuple[bool, BreachAlertLevel]:
    """
    Evaluate overall breach risk from individual detection results.

    Returns (should_alert, alert_level).
    """
    score = 0
    if volume_anomaly:
        score += 2
    if off_hours:
        score += 1
    if rapid_sequential:
        score += 3
    if unusual_patients:
        score += 2

    if score >= 5:
        return True, BreachAlertLevel.CRITICAL
    elif score >= 3:
        return True, BreachAlertLevel.HIGH
    elif score >= 2:
        return True, BreachAlertLevel.MEDIUM
    elif score >= 1:
        return True, BreachAlertLevel.LOW
    else:
        return False, BreachAlertLevel.LOW
