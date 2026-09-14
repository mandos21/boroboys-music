import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Disc3 } from "lucide-react";

import { post } from "../../api/client";
import type { components } from "../../api/schema";
import { Button } from "../../components/ui/button";
import { useToast } from "../../components/ui/ToastProvider";
import "./attribution.css";
import { ContributorAvatar } from "./ContributorAvatar";
import type { AttributionRosterMember, AttributionStatus, AttributionSubmitResult } from "./types";

type Submission = components["schemas"]["SubmissionResponse"];

type AttributionGameProps = {
  roundId: string;
  status: AttributionStatus;
  tracks: Submission[];
  onRevealed: () => void;
};

function formatCountdown(revealAt: string, now: number): string {
  const milliseconds = new Date(revealAt).getTime() - now;
  if (milliseconds <= 0) return "revealing any moment";
  const totalMinutes = Math.ceil(milliseconds / 60_000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function AttributionCountdown({ revealAt }: { revealAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span className="attribution-countdown">
      Names reveal in <strong>{formatCountdown(revealAt, now)}</strong>
    </span>
  );
}

function TrackChip({
  submission,
  selected,
  onSelect,
  onDragStart,
}: {
  submission: Submission;
  selected: boolean;
  onSelect: () => void;
  onDragStart: () => void;
}) {
  return (
    <button
      type="button"
      className={`attribution-track-chip${selected ? " selected" : ""}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", submission.id);
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onClick={onSelect}
      aria-pressed={selected}
    >
      {submission.track.artworkUrl ? (
        <img src={submission.track.artworkUrl} alt="" />
      ) : (
        <span className="attribution-track-chip-placeholder" aria-hidden="true">
          <Disc3 size={16} />
        </span>
      )}
      <span>
        <strong>{submission.track.name}</strong>
        <small>{submission.track.artist}</small>
      </span>
    </button>
  );
}

function OwnTrackChip({ submission }: { submission: Submission }) {
  return (
    <div className="attribution-track-chip attribution-track-chip-readonly">
      {submission.track.artworkUrl ? (
        <img src={submission.track.artworkUrl} alt="" />
      ) : (
        <span className="attribution-track-chip-placeholder" aria-hidden="true">
          <Disc3 size={16} />
        </span>
      )}
      <span>
        <strong>{submission.track.name}</strong>
        <small>{submission.track.artist}</small>
      </span>
    </div>
  );
}

function OwnTracks({ tracks }: { tracks: Submission[] }) {
  if (tracks.length === 0) return null;
  return (
    <div className="attribution-own-tracks">
      <p className="attribution-own-tracks-label">
        Your own {tracks.length === 1 ? "pick is" : "picks are"} filled in automatically - nothing
        to guess here.
      </p>
      <div className="attribution-tray attribution-own-tray" aria-label="Your own submissions">
        {tracks.map((entry) => (
          <OwnTrackChip key={entry.id} submission={entry} />
        ))}
      </div>
    </div>
  );
}

function RosterBin({
  member,
  assignedCount,
  assignedTracks,
  selectedTrackId,
  onSelectTrack,
  onDropHere,
  onTapHere,
  onRemove,
}: {
  member: AttributionRosterMember;
  assignedCount: number;
  assignedTracks: Submission[];
  selectedTrackId: string | null;
  onSelectTrack: (id: string) => void;
  onDropHere: () => void;
  onTapHere: () => void;
  onRemove: (submissionId: string) => void;
}) {
  const full = assignedCount >= member.maxGuesses;
  return (
    <div
      className={`attribution-roster-bin${full ? " full" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        onDropHere();
      }}
    >
      <button type="button" className="attribution-roster-header" onClick={onTapHere}>
        <ContributorAvatar member={member.contributor} />
        <span>
          <strong>{member.contributor.displayName}</strong>
          <small>
            {assignedCount} of {member.maxGuesses} placed
          </small>
        </span>
      </button>
      {assignedTracks.length > 0 && (
        <ul className="attribution-roster-tracks">
          {assignedTracks.map((track) => (
            <li key={track.id}>
              <TrackChip
                submission={track}
                selected={selectedTrackId === track.id}
                onSelect={() => onSelectTrack(track.id)}
                onDragStart={() => onSelectTrack(track.id)}
              />
              <button
                type="button"
                className="attribution-unassign"
                onClick={() => onRemove(track.id)}
                aria-label={`Unassign ${track.track.name}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function scoreTitle(percent: number): string {
  if (percent === 100) return "Mind reader";
  if (percent >= 75) return "Music detective";
  if (percent >= 50) return "Solid guesser";
  if (percent >= 25) return "Casual listener";
  return "Tone deaf (affectionately)";
}

function AttributionReveal({
  result,
  roster,
  tracks,
  onContinue,
}: {
  result: AttributionSubmitResult;
  roster: AttributionRosterMember[];
  tracks: Submission[];
  onContinue: () => void;
}) {
  const [flipped, setFlipped] = useState<Set<string>>(new Set());
  useEffect(() => {
    const timers = result.results.map((outcome, index) =>
      window.setTimeout(() => {
        setFlipped((current) => new Set(current).add(outcome.submissionId));
      }, 180 * index),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [result]);

  const percent =
    result.totalCount === 0 ? 100 : Math.round((result.correctCount / result.totalCount) * 100);
  const contributorsById = new Map(
    roster.map((member) => [member.contributor.id, member.contributor]),
  );
  const tracksById = new Map(tracks.map((track) => [track.id, track]));

  return (
    <section className="panel attribution-reveal" aria-live="polite">
      <div className="attribution-score">
        <strong>
          {result.correctCount} / {result.totalCount}
        </strong>
        <span>
          {percent}% — {scoreTitle(percent)}
        </span>
      </div>
      <ul className="attribution-flip-grid">
        {result.results.map((outcome) => {
          const track = tracksById.get(outcome.submissionId);
          const guessed = contributorsById.get(outcome.guessedContributorId);
          const actual = contributorsById.get(outcome.actualContributorId);
          if (!track) return null;
          return (
            <li
              key={outcome.submissionId}
              className={`attribution-flip-card${flipped.has(outcome.submissionId) ? " flipped" : ""}${
                outcome.isCorrect ? " correct" : " incorrect"
              }`}
            >
              <div className="attribution-flip-card-inner">
                <div className="attribution-flip-face attribution-flip-front">
                  {track.track.artworkUrl ? (
                    <img src={track.track.artworkUrl} alt="" />
                  ) : (
                    <Disc3 aria-hidden="true" size={22} />
                  )}
                  <strong>{track.track.name}</strong>
                  <span>Your guess: {guessed?.displayName ?? "—"}</span>
                </div>
                <div className="attribution-flip-face attribution-flip-back">
                  <strong>{track.track.name}</strong>
                  <span>
                    {outcome.isCorrect
                      ? "Correct!"
                      : `Actually ${actual?.displayName ?? "unknown"}`}
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <Button onClick={onContinue}>See the full submissions</Button>
    </section>
  );
}

export function AttributionGame({ roundId, status, tracks, onRevealed }: AttributionGameProps) {
  const { showToast } = useToast();
  const guessable = useMemo(() => tracks.filter((entry) => !entry.isMine), [tracks]);
  const ownTracks = useMemo(() => tracks.filter((entry) => entry.isMine), [tracks]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [result, setResult] = useState<AttributionSubmitResult | null>(null);

  const countsByContributor = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const contributorId of Object.values(assignments)) {
      counts[contributorId] = (counts[contributorId] ?? 0) + 1;
    }
    return counts;
  }, [assignments]);

  const submit = useMutation({
    mutationFn: () =>
      post<AttributionSubmitResult>(`/rounds/${roundId}/attribution/guesses`, {
        guesses: guessable.map((entry) => ({
          submission_id: entry.id,
          contributor_id: assignments[entry.id],
        })),
      }),
    onSuccess: (data) => setResult(data),
    onError: () =>
      showToast({
        title: "Couldn’t submit your guesses",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });

  if (result) {
    return (
      <AttributionReveal
        result={result}
        roster={status.roster}
        tracks={guessable}
        onContinue={onRevealed}
      />
    );
  }

  if (guessable.length === 0) {
    return (
      <section className="panel attribution-game">
        <p className="eyebrow">Guess Who?</p>
        <h2>Nobody else to guess yet</h2>
        {status.revealAt && (
          <p>
            Names for the rest of the group reveal in{" "}
            <AttributionCountdown revealAt={status.revealAt} />.
          </p>
        )}
        <OwnTracks tracks={ownTracks} />
      </section>
    );
  }

  function capacityFor(contributorId: string): number {
    return status.roster.find((member) => member.contributor.id === contributorId)?.maxGuesses ?? 0;
  }

  function tryAssign(submissionId: string, contributorId: string) {
    const alreadyThere = assignments[submissionId] === contributorId;
    if (alreadyThere) return;
    if ((countsByContributor[contributorId] ?? 0) >= capacityFor(contributorId)) {
      showToast({
        title: "That's as many as they could have submitted",
        description: "This member's guessed total already matches this round's submission limit.",
        tone: "error",
      });
      return;
    }
    setAssignments((current) => ({ ...current, [submissionId]: contributorId }));
    setSelectedTrackId(null);
    setDraggingId(null);
  }

  function unassign(submissionId: string) {
    setAssignments((current) => {
      const next = { ...current };
      delete next[submissionId];
      return next;
    });
  }

  const unassignedTracks = guessable.filter((entry) => !assignments[entry.id]);
  const placedCount = guessable.length - unassignedTracks.length;
  const allPlaced = unassignedTracks.length === 0;

  return (
    <section className="panel attribution-game" aria-labelledby="attribution-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Guess Who?</p>
          <h2 id="attribution-heading">Guess who submitted what</h2>
        </div>
        {status.revealAt && <AttributionCountdown revealAt={status.revealAt} />}
      </div>
      <p className="attribution-instructions">
        Drag a track onto a name, or tap a track and then tap a name. Lock in your answers to see
        how you did — right away, before everyone else's names reveal.
      </p>
      <OwnTracks tracks={ownTracks} />
      <div
        className="attribution-tray"
        aria-label="Unassigned tracks"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (draggingId) unassign(draggingId);
          setDraggingId(null);
        }}
      >
        {unassignedTracks.length > 0 ? (
          unassignedTracks.map((entry) => (
            <TrackChip
              key={entry.id}
              submission={entry}
              selected={selectedTrackId === entry.id}
              onSelect={() => setSelectedTrackId((id) => (id === entry.id ? null : entry.id))}
              onDragStart={() => setDraggingId(entry.id)}
            />
          ))
        ) : (
          <p className="attribution-tray-empty">
            Every track has a guess. Review the names below, then lock it in.
          </p>
        )}
      </div>
      <div className="attribution-roster">
        {status.roster.map((member) => (
          <RosterBin
            key={member.contributor.id}
            member={member}
            assignedCount={countsByContributor[member.contributor.id] ?? 0}
            assignedTracks={guessable.filter(
              (entry) => assignments[entry.id] === member.contributor.id,
            )}
            selectedTrackId={selectedTrackId}
            onSelectTrack={(id) => setSelectedTrackId((current) => (current === id ? null : id))}
            onDropHere={() => draggingId && tryAssign(draggingId, member.contributor.id)}
            onTapHere={() => selectedTrackId && tryAssign(selectedTrackId, member.contributor.id)}
            onRemove={unassign}
          />
        ))}
      </div>
      <div className="attribution-actions">
        <span>
          {placedCount} of {guessable.length} placed
        </span>
        <Button disabled={!allPlaced || submit.isPending} onClick={() => submit.mutate()}>
          {submit.isPending ? "Locking in…" : "Lock in my guesses"}
        </Button>
      </div>
    </section>
  );
}
