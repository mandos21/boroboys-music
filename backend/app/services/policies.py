"""Versioned, explainable submission policy evaluation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvaluationDecision, Round, Submission, SubmissionStatus


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
        if kind == "duplicate_in_round":
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
