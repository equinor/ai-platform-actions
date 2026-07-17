"""Validation for monitoring evidence used by autonomous outer-loop decisions."""

from datetime import datetime, timedelta, timezone
from typing import Optional


def validate_monitoring_evidence(
    monitoring_run: Optional[dict],
    *,
    model_name: Optional[str],
    model_version: Optional[str],
    endpoint_name: Optional[str],
    deployment_name: Optional[str],
    max_age: timedelta,
    min_sample_count: int,
    now: Optional[datetime] = None,
) -> list[str]:
    """Return reasons why a monitoring run cannot support an autonomous decision."""
    if monitoring_run is None:
        return ["no monitoring run found"]

    issues: list[str] = []
    tags = monitoring_run.get("tags", {})
    metrics = monitoring_run.get("metrics", {})

    if tags.get("aip.monitoring.schema_version") != "1":
        issues.append("unsupported or missing monitoring schema version")

    expected_tags = {
        "aip.model.name": model_name,
        "aip.model.version": model_version,
        "aip.endpoint.name": endpoint_name,
        "aip.deployment.name": deployment_name,
    }
    for tag_name, expected_value in expected_tags.items():
        if expected_value is None:
            continue
        actual_value = tags.get(tag_name)
        if actual_value != expected_value:
            issues.append(
                f"{tag_name} mismatch: expected {expected_value!r}, got {actual_value!r}"
            )

    observed_at_raw = tags.get("aip.observed_at")
    if not observed_at_raw:
        issues.append("missing aip.observed_at")
    else:
        try:
            observed_at = datetime.fromisoformat(observed_at_raw.replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                raise ValueError("timezone is required")
            reference_time = now or datetime.now(timezone.utc)
            if observed_at > reference_time + timedelta(minutes=5):
                issues.append("aip.observed_at is in the future")
            elif reference_time - observed_at > max_age:
                issues.append("monitoring evidence is stale")
        except (TypeError, ValueError):
            issues.append("invalid aip.observed_at; expected timezone-aware ISO 8601")

    sample_count = metrics.get("sample_count")
    if not isinstance(sample_count, (int, float)) or sample_count < min_sample_count:
        issues.append(
            f"sample_count must be at least {min_sample_count}, got {sample_count!r}"
        )

    return issues