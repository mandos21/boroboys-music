"""Contributor-visible round endpoints, split by what a person is doing.

The modules share one router and are imported for the side effect of
registering routes on it. Route functions and input models are re-exported
because the tests call them directly rather than through HTTP.
"""

from app.api.routes.rounds._common import TrackInput, _may_see_evidence, router
from app.api.routes.rounds.discovery import (
    get_evidence,
    get_listening_suggestions,
    list_round_submission_counts,
    list_round_submissions,
    search_tracks,
)
from app.api.routes.rounds.rounds import (
    RoundParticipationUpdate,
    SubmissionDraftUpdate,
    get_round,
    get_submission_draft,
    list_my_rounds,
    save_submission_draft,
    update_round_participation,
)
from app.api.routes.rounds.submissions import (
    SubmissionCreate,
    SubmissionUpdate,
    TrackEvaluationRequest,
    create_submission,
    evaluate_track,
    update_submission,
    withdraw_submission,
)

__all__ = [
    "RoundParticipationUpdate",
    "SubmissionCreate",
    "SubmissionDraftUpdate",
    "SubmissionUpdate",
    "TrackEvaluationRequest",
    "TrackInput",
    "_may_see_evidence",
    "create_submission",
    "evaluate_track",
    "get_evidence",
    "get_listening_suggestions",
    "get_round",
    "get_submission_draft",
    "list_my_rounds",
    "list_round_submission_counts",
    "list_round_submissions",
    "router",
    "save_submission_draft",
    "search_tracks",
    "update_round_participation",
    "update_submission",
    "withdraw_submission",
]
