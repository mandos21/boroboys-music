"""Versioned, explainable submission policy evaluation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    EvaluationDecision,
    Round,
    RoundStatus,
    Submission,
    SubmissionStatus,
    Track,
)


@dataclass(frozen=True)
class PolicyResult:
    kind: str
    version: str
    decision: EvaluationDecision
    message: str
    result: dict[str, Any]


def evaluate_submission(
    db: Session, round_: Round, track_id: uuid.UUID, policies: list[dict[str, Any]]
) -> list[PolicyResult]:
    results: list[PolicyResult] = []
    for policy in policies:
        if not policy.get("enabled", True):
            continue
        kind = policy.get("kind")
        if kind in {"duplicate_in_round", "no_duplicate_in_round"}:
            duplicate = db.scalar(
                select(Submission.id).where(
                    Submission.round_id == round_.id,
                    Submission.track_id == track_id,
                    Submission.status == SubmissionStatus.ACCEPTED,
                )
            )
            if duplicate:
                results.append(
                    PolicyResult(
                        kind=kind,
                        version="1",
                        decision=_decision(policy),
                        message="This track is already submitted in this round.",
                        result={"existingSubmissionId": str(duplicate)},
                    )
                )
        elif kind == "duplicate_in_series":
            duplicate = db.scalar(
                select(Submission.id)
                .join(Round, Submission.round_id == Round.id)
                .where(
                    Round.series_id == round_.series_id,
                    Submission.track_id == track_id,
                    Submission.status == SubmissionStatus.ACCEPTED,
                )
                .limit(1)
            )
            if duplicate:
                results.append(
                    PolicyResult(
                        kind=kind,
                        version="1",
                        decision=_decision(policy),
                        message="This track has already appeared in this series.",
                        result={"existingSubmissionId": str(duplicate)},
                    )
                )
        elif kind == "no_recent_series_repeat":
            lookback_rounds = _positive_int(policy.get("lookback_rounds"), default=1)
            recent_rounds = select(Round.id).where(
                Round.series_id == round_.series_id,
                Round.status == RoundStatus.PUBLISHED,
                Round.published_sequence.is_not(None),
            ).order_by(Round.published_sequence.desc()).limit(lookback_rounds)
            duplicate = db.scalar(
                select(Submission.id)
                .where(
                    Submission.round_id.in_(recent_rounds),
                    Submission.track_id == track_id,
                    Submission.status == SubmissionStatus.ACCEPTED,
                )
                .limit(1)
            )
            if duplicate:
                results.append(
                    PolicyResult(
                        kind=kind,
                        version="1",
                        decision=_decision(policy),
                        message=(
                            "This track appeared in one of the last "
                            f"{lookback_rounds} published rounds."
                        ),
                        result={
                            "existingSubmissionId": str(duplicate),
                            "lookbackRounds": lookback_rounds,
                        },
                    )
                )
        elif kind == "explicit_content":
            track = db.get(Track, track_id)
            if track is not None and track.provider_metadata.get("explicit") is True:
                results.append(
                    PolicyResult(
                        kind=kind,
                        version="1",
                        decision=_decision(policy),
                        message="This track is marked explicit by Spotify.",
                        result={"explicit": True},
                    )
                )
        elif kind == "track_availability":
            track = db.get(Track, track_id)
            if track is not None and track.provider_metadata.get("isPlayable") is False:
                results.append(
                    PolicyResult(
                        kind=kind,
                        version="1",
                        decision=_decision(policy),
                        message="Spotify reports this track is unavailable to the current account.",
                        result={"isPlayable": False},
                    )
                )
        elif kind:
            results.append(
                PolicyResult(
                    kind=str(kind),
                    version="1",
                    decision=EvaluationDecision.WARN,
                    message="This policy is not installed on this server.",
                    result={"status": "unsupported"},
                )
            )
    return results


def _decision(policy: dict[str, Any]) -> EvaluationDecision:
    value = policy.get("on_match", EvaluationDecision.REJECT.value)
    try:
        return EvaluationDecision(value)
    except ValueError:
        return EvaluationDecision.REJECT


def _positive_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default
