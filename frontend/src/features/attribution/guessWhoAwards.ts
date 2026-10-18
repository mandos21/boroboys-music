import type { AttributionLeaderboardEntry, AttributionSubmitterBreakdown } from "./types";

type Person = AttributionSubmitterBreakdown["contributor"];
export type GuessWhoAward = {
  title: string;
  variant: string;
  detail: string;
  explanation: string;
  people: Person[];
  strength: number;
  lane: number;
};

const pct = (value: number) => `${Math.round(value * 100)}%`;
const plural = (count: number, word: string) =>
  `${count} ${word}${count === 1 ? "" : word.endsWith("guess") ? "es" : "s"}`;

/** All scores are ratios, so larger rounds do not win awards merely through turnout. */
export function guessWhoAwards(
  entries: AttributionSubmitterBreakdown[],
  leaderboard: AttributionLeaderboardEntry[],
): GuessWhoAward[] {
  const total = entries.reduce((sum, entry) => sum + entry.groupTotalCount, 0);
  if (!total) return [];
  const correct = entries.reduce((sum, entry) => sum + entry.groupCorrectCount, 0);
  const average = correct / total;
  const candidates: GuessWhoAward[] = [];
  const add = (award: GuessWhoAward) => candidates.push(award);
  const eligibleGuesser = leaderboard.filter((row) => row.totalCount > 0);
  const best = [...eligibleGuesser].sort(
    (a, b) => b.correctCount / b.totalCount - a.correctCount / a.totalCount,
  )[0];
  const worst = [...eligibleGuesser].sort(
    (a, b) => a.correctCount / a.totalCount - b.correctCount / b.totalCount,
  )[0];
  if (best && best.correctCount / best.totalCount >= Math.max(0.6, average + 0.15)) {
    const rate = best.correctCount / best.totalCount;
    add({
      title: "Detective",
      variant: "detective",
      detail: "Had the sharpest ear.",
      explanation: `${pct(rate)} of guesses correct`,
      people: eligibleGuesser
        .filter((row) => row.correctCount / row.totalCount === rate)
        .map((row) => row.contributor),
      strength: rate - average,
      lane: 0,
    });
  }
  if (worst && worst.correctCount / worst.totalCount <= average - 0.15) {
    const rate = worst.correctCount / worst.totalCount;
    add({
      title: "Stumped",
      variant: "stumped",
      detail: "Followed a few false leads.",
      explanation: `${pct(rate)} of guesses correct`,
      people: eligibleGuesser
        .filter((row) => row.correctCount / row.totalCount === rate)
        .map((row) => row.contributor),
      strength: average - rate,
      lane: 0,
    });
  }
  const recognized = entries.filter((entry) => entry.groupTotalCount > 0);
  const most = [...recognized].sort(
    (a, b) => b.groupCorrectCount / b.groupTotalCount - a.groupCorrectCount / a.groupTotalCount,
  )[0];
  const least = [...recognized].sort(
    (a, b) => a.groupCorrectCount / a.groupTotalCount - b.groupCorrectCount / b.groupTotalCount,
  )[0];
  if (most && most.groupCorrectCount / most.groupTotalCount >= average + 0.15) {
    const rate = most.groupCorrectCount / most.groupTotalCount;
    add({
      title: "Well-Known",
      variant: "well-known",
      detail: "Their picks sounded like them.",
      explanation: `${pct(rate)} of guesses on their tracks were correct`,
      people: recognized
        .filter((row) => row.groupCorrectCount / row.groupTotalCount === rate)
        .map((row) => row.contributor),
      strength: rate - average,
      lane: 1,
    });
  }
  if (least && least.groupCorrectCount / least.groupTotalCount <= average - 0.15) {
    const rate = least.groupCorrectCount / least.groupTotalCount;
    add({
      title: "Elusive",
      variant: "elusive",
      detail: "Kept the room guessing.",
      explanation: `${pct(rate)} of guesses on their tracks were correct`,
      people: recognized
        .filter((row) => row.groupCorrectCount / row.groupTotalCount === rate)
        .map((row) => row.contributor),
      strength: average - rate,
      lane: 1,
    });
  }
  const byId = new Map<string, Person>();
  for (const entry of entries) {
    byId.set(entry.contributor.id, entry.contributor);
    for (const song of entry.songs)
      for (const guess of song.guesses)
        byId.set(guess.guessedContributor.id, guess.guessedContributor);
  }
  const pairs = new Map<string, number>();
  for (const entry of entries)
    for (const song of entry.songs)
      for (const guess of song.guesses) {
        if (guess.isCorrect) continue;
        const key = `${entry.contributor.id}|${guess.guessedContributor.id}`;
        pairs.set(key, (pairs.get(key) ?? 0) + 1);
      }
  const imposter = [...pairs]
    .map(([key, count]) => {
      const [actual, mistaken] = key.split("|");
      const incoming =
        entries.find((entry) => entry.contributor.id === actual)?.groupTotalCount ?? 0;
      return { actual, mistaken, count, incoming, rate: incoming ? count / incoming : 0 };
    })
    .sort((a, b) => b.rate - a.rate || b.count - a.count)[0];
  if (imposter && imposter.rate >= 0.25) {
    add({
      title: "Imposter",
      variant: "imposter",
      detail: `Often mistaken for ${byId.get(imposter.mistaken)?.displayName ?? "someone else"}.`,
      explanation: `${plural(imposter.count, "guess")} out of ${imposter.incoming} named ${byId.get(imposter.mistaken)?.displayName ?? "another person"}`,
      people: [byId.get(imposter.actual)!],
      strength: imposter.rate,
      lane: 2,
    });
  }
  const reciprocal = [...pairs]
    .flatMap(([key, count]) => {
      const [a, b] = key.split("|");
      if (a >= b) return [];
      const reverse = pairs.get(`${b}|${a}`) ?? 0;
      if (!reverse) return [];
      const denominator =
        (entries.find((entry) => entry.contributor.id === a)?.groupTotalCount ?? 0) +
        (entries.find((entry) => entry.contributor.id === b)?.groupTotalCount ?? 0);
      return [
        { a, b, count: count + reverse, rate: denominator ? (count + reverse) / denominator : 0 },
      ];
    })
    .sort((a, b) => b.rate - a.rate)[0];
  if (reciprocal && reciprocal.rate >= 0.2) {
    add({
      title: "Doppelgängers",
      variant: "doppelgangers",
      detail: "The room kept mixing them up.",
      explanation: `${plural(reciprocal.count, "crossed guess")} between them`,
      people: [byId.get(reciprocal.a)!, byId.get(reciprocal.b)!],
      strength: reciprocal.rate,
      lane: 2,
    });
  }
  const songs = entries.flatMap((entry) => entry.songs.map((song) => ({ entry, song })));
  const unanimous = songs
    .filter(
      ({ song }) => song.groupTotalCount > 0 && song.groupCorrectCount === song.groupTotalCount,
    )
    .sort((a, b) => b.song.groupTotalCount - a.song.groupTotalCount)[0];
  if (unanimous)
    add({
      title: "Unanimous",
      variant: "unanimous",
      detail: `Every player so far recognized “${unanimous.song.track.name}.”`,
      explanation: `${plural(unanimous.song.groupTotalCount, "correct guess")}`,
      people: [unanimous.entry.contributor],
      strength: 1,
      lane: 3,
    });
  const twists = songs
    .flatMap(({ entry, song }) => {
      if (song.groupTotalCount === 0) return [];
      const counts = new Map<string, number>();
      for (const guess of song.guesses)
        if (!guess.isCorrect)
          counts.set(
            guess.guessedContributor.id,
            (counts.get(guess.guessedContributor.id) ?? 0) + 1,
          );
      return [...counts]
        .filter(([, count]) => count / song.groupTotalCount >= 0.6)
        .map(([id, count]) => ({ entry, song, id, count, rate: count / song.groupTotalCount }));
    })
    .sort((a, b) => b.rate - a.rate || b.count - a.count)[0];
  if (twists)
    add({
      title: "Plot Twist",
      variant: "plot-twist",
      detail: `“${twists.song.track.name}” sounded like ${byId.get(twists.id)?.displayName ?? "someone else"}.`,
      explanation: `${twists.count} of ${twists.song.groupTotalCount} guesses named someone else`,
      people: [twists.entry.contributor],
      strength: twists.rate,
      lane: 3,
    });
  const split = songs
    .map(({ entry, song }) => {
      const counts = new Map<string, number>();
      for (const guess of song.guesses)
        counts.set(guess.guessedContributor.id, (counts.get(guess.guessedContributor.id) ?? 0) + 1);
      const largest = Math.max(0, ...counts.values());
      return {
        entry,
        song,
        choices: counts.size,
        score: song.groupTotalCount ? 1 - largest / song.groupTotalCount : 0,
      };
    })
    .filter((row) => row.choices >= 3 && row.score >= 0.5)
    .sort((a, b) => b.score - a.score || b.choices - a.choices)[0];
  if (split)
    add({
      title: "Split Decision",
      variant: "split-decision",
      detail: `“${split.song.track.name}” sent guesses in every direction.`,
      explanation: `${plural(split.choices, "different person")} named`,
      people: [split.entry.contributor],
      strength: split.score,
      lane: 3,
    });
  // Preserve variety first; use strength to decide between awards in a lane.
  const selected: GuessWhoAward[] = [];
  const repeatsStory = (award: GuessWhoAward) =>
    selected.some(
      (other) =>
        ["Imposter", "Plot Twist"].includes(other.title) &&
        ["Imposter", "Plot Twist"].includes(award.title) &&
        other.people[0]?.id === award.people[0]?.id,
    );
  // Pick the specific mistaken-identity story first, then prefer a different
  // person when two recognizability findings are equally strong.
  for (const lane of [2, 1, 0, 3]) {
    const winner = candidates
      .filter((award) => award.lane === lane)
      .sort((a, b) => {
        const score = (award: GuessWhoAward) =>
          award.strength -
          (selected.some((other) => other.people[0]?.id === award.people[0]?.id) ? 0.04 : 0);
        return score(b) - score(a) || a.title.localeCompare(b.title);
      })
      .find((award) => !repeatsStory(award));
    if (winner) selected.push(winner);
  }
  const extras = candidates
    .filter((award) => !selected.includes(award))
    .sort((a, b) => b.strength - a.strength || a.title.localeCompare(b.title));
  for (const award of extras) {
    if (selected.length === 4) break;
    // Imposter and Plot Twist can describe the same mistaken pair and track.
    if (repeatsStory(award)) continue;
    selected.push(award);
  }
  return selected.sort((a, b) => a.lane - b.lane);
}
