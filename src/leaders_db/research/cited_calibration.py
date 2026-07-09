"""Calibration validation for cited manual/internet evaluations."""

from __future__ import annotations

from typing import Any

RUBRIC_VERSION_BY_METHODOLOGY_ID = {
    "4B.1": "4b1_electoral_contestability_v1",
    "4B.2": "4b2_entrenchment_manipulation_v1",
    "4B.3": "4b3_opposition_tolerance_v1",
}

CALIBRATION_REQUIRED_FIELDS = (
    "rubric_version",
    "calibration_batch_id",
    "calibrated_against",
    "severity_band",
    "state_responsibility",
    "accountability_level",
    "information_environment",
    "period_fit",
    "source_mix",
    "structured_prior_summary",
    "contrary_evidence",
    "score_rationale",
    "lower_anchor_rejected",
    "higher_anchor_rejected",
    "visibility_bias_check",
    "repression_silence_check",
    "population_scale_check",
    "source_type_check",
    "recency_check",
    "subagent_calibration_check",
)

CALIBRATION_ENUM_FIELDS = {
    "severity_band": {"none", "isolated", "recurring", "widespread", "systematic", "mass"},
    "state_responsibility": {
        "direct",
        "state_aligned",
        "tolerated",
        "failed_to_prevent",
        "non_state_only",
        "unclear",
    },
    "accountability_level": {
        "strong",
        "partial",
        "weak",
        "none",
        "perpetrator_impunity",
        "state_policy",
    },
    "information_environment": {
        "open",
        "partly_restricted",
        "closed",
        "highly_repressive",
        "unclear",
    },
    "period_fit": {"target_year", "ruler_period", "near_period", "outside_period", "unclear"},
}

CALIBRATION_REQUIRED_FIELDS_BY_METHODOLOGY_ID = {
    "4B.1": (
        "electoral_system_status",
        "incumbent_acceptance_of_loss",
        "contestability_constraints",
    ),
    "4B.2": (
        "manipulation_status",
        "entrenchment_channels",
        "institutional_remedy_status",
    ),
    "4B.3": (
        "tolerance_status",
        "opposition_tolerance_channels",
        "remedy_or_accountability_status",
    ),
}

CALIBRATION_ENUM_FIELDS_BY_METHODOLOGY_ID = {
    "4B.1": {
        "electoral_system_status": {
            "no_meaningful_elections",
            "sham_elections",
            "hegemonic_elections",
            "competitive_but_unfair",
            "competitive_with_flaws",
            "free_and_fair",
            "unclear",
        },
        "incumbent_acceptance_of_loss": {
            "accepted",
            "partially_accepted",
            "not_tested",
            "rejected",
            "prevented_test",
            "unclear",
        },
    },
    "4B.2": {
        "manipulation_status": {
            "none_found",
            "isolated_or_alleged",
            "recurring_advantage",
            "systematic_entrenchment",
            "no_meaningful_constraints",
            "not_applicable",
            "unclear",
        },
        "institutional_remedy_status": {
            "effective",
            "partial",
            "weak",
            "captured",
            "not_applicable",
            "unclear",
        },
    },
    "4B.3": {
        "tolerance_status": {
            "protected",
            "mostly_tolerated",
            "selectively_restricted",
            "recurring_repression",
            "systematic_repression",
            "no_meaningful_space",
            "unclear",
        },
        "remedy_or_accountability_status": {
            "effective",
            "partial",
            "weak",
            "none",
            "state_policy",
            "not_applicable",
            "unclear",
        },
    },
}

CALIBRATION_LIST_FIELDS_BY_METHODOLOGY_ID = {
    "4B.1": ("contestability_constraints",),
    "4B.2": ("entrenchment_channels",),
    "4B.3": ("opposition_tolerance_channels",),
}

CALIBRATION_LIST_VALUE_FIELDS_BY_METHODOLOGY_ID = {
    "4B.1": {
        "contestability_constraints": {
            "candidate_bans",
            "opposition_arrests",
            "media_capture",
            "fraud",
            "state_resource_abuse",
            "violence_intimidation",
            "captured_election_body",
            "captured_courts",
            "internet_shutdowns",
            "none_found",
        }
    },
    "4B.2": {
        "entrenchment_channels": {
            "electoral_rules",
            "courts",
            "media",
            "election_commission",
            "security_forces",
            "public_resources",
            "constitutional_or_term_limit_change",
            "party_or_legislature_capture",
            "none_found",
            "not_applicable",
            "unclear",
        }
    },
    "4B.3": {
        "opposition_tolerance_channels": {
            "opposition_victories",
            "criticism_or_satire",
            "investigative_journalism",
            "protest",
            "civil_society_monitoring",
            "media_pressure",
            "legal_or_administrative_harassment",
            "security_force_intimidation",
            "internet_or_information_controls",
            "none_found",
            "not_applicable",
            "unclear",
        }
    },
}


def validate_score_calibration(
    *,
    methodology_id: str | None = None,
    score_1_to_10: int | None,
    answer_payload: dict[str, Any],
) -> None:
    """Require common-meter calibration metadata for score-bearing evaluations."""

    if score_1_to_10 is None:
        return

    calibration = answer_payload.get("calibration")
    if not isinstance(calibration, dict):
        raise ValueError("answer_payload.calibration is required when score_1_to_10 is set")

    required_fields = _required_calibration_fields(methodology_id)
    missing = [field for field in required_fields if field not in calibration]
    if missing:
        raise ValueError(f"answer_payload.calibration is missing required fields: {missing}")

    _validate_expected_rubric_version(calibration, methodology_id)
    _validate_calibration_enum_fields(calibration, methodology_id)
    _validate_calibration_list_fields(calibration, methodology_id)

    if not calibration["calibrated_against"]:
        raise ValueError("answer_payload.calibration.calibrated_against must not be empty")

    if not calibration["source_mix"]:
        raise ValueError("answer_payload.calibration.source_mix must not be empty")


def _required_calibration_fields(methodology_id: str | None) -> tuple[str, ...]:
    if methodology_id is None:
        return CALIBRATION_REQUIRED_FIELDS
    return CALIBRATION_REQUIRED_FIELDS + CALIBRATION_REQUIRED_FIELDS_BY_METHODOLOGY_ID.get(
        methodology_id, ()
    )


def _validate_expected_rubric_version(
    calibration: dict[str, Any], methodology_id: str | None
) -> None:
    expected = RUBRIC_VERSION_BY_METHODOLOGY_ID.get(methodology_id or "")
    if expected is None:
        return
    actual = calibration["rubric_version"]
    if actual != expected:
        raise ValueError(
            "answer_payload.calibration.rubric_version must be "
            f"{expected!r} for methodology_id {methodology_id!r}; got {actual!r}"
        )


def _validate_calibration_enum_fields(
    calibration: dict[str, Any],
    methodology_id: str | None,
) -> None:
    enum_fields = dict(CALIBRATION_ENUM_FIELDS)
    if methodology_id is not None:
        enum_fields.update(CALIBRATION_ENUM_FIELDS_BY_METHODOLOGY_ID.get(methodology_id, {}))

    for field, allowed_values in enum_fields.items():
        value = calibration[field]
        if value not in allowed_values:
            raise ValueError(
                f"answer_payload.calibration.{field} must be one of {sorted(allowed_values)}"
            )


def _validate_calibration_list_fields(
    calibration: dict[str, Any],
    methodology_id: str | None,
) -> None:
    list_fields = ("calibrated_against", "source_mix", "contrary_evidence")
    if methodology_id is not None:
        list_fields += CALIBRATION_LIST_FIELDS_BY_METHODOLOGY_ID.get(methodology_id, ())

    for field in list_fields:
        if not isinstance(calibration[field], list):
            raise ValueError(f"answer_payload.calibration.{field} must be a list")

    if methodology_id is None:
        return

    for field, allowed_values in CALIBRATION_LIST_VALUE_FIELDS_BY_METHODOLOGY_ID.get(
        methodology_id, {}
    ).items():
        invalid_values = [value for value in calibration[field] if value not in allowed_values]
        if invalid_values:
            raise ValueError(
                f"answer_payload.calibration.{field} contains invalid values: {invalid_values}"
            )


__all__ = [
    "CALIBRATION_REQUIRED_FIELDS",
    "CALIBRATION_REQUIRED_FIELDS_BY_METHODOLOGY_ID",
    "RUBRIC_VERSION_BY_METHODOLOGY_ID",
    "validate_score_calibration",
]
