/** Timezone-safe helpers for native datetime-local controls.
 *
 * A datetime-local value is a wall-clock value with no offset. Series schedules
 * are defined in their configured IANA timezone, not in an administrator's
 * browser timezone, so `new Date(value)` is deliberately never used here.
 */
type WallParts = { year: number; month: number; day: number; hour: number; minute: number };

function parseWall(value: string): WallParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  if (!year || !month || !day || hour === undefined || minute === undefined) return null;
  return { year, month, day, hour, minute };
}

function wallPartsAt(date: Date, timeZone: string): WallParts {
  const values = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date).reduce<Record<string, string>>((result, part) => {
    result[part.type] = part.value;
    return result;
  }, {});
  return {
    year: Number(values.year), month: Number(values.month), day: Number(values.day),
    hour: Number(values.hour), minute: Number(values.minute),
  };
}

function wallValue(parts: WallParts): string {
  return `${String(parts.year).padStart(4, "0")}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}T${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
}

function offsetAt(date: Date, timeZone: string): number {
  const parts = wallPartsAt(date, timeZone);
  return Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute) - date.getTime();
}

export function toZonedInput(value: string | Date, timeZone: string): string {
  return wallValue(wallPartsAt(new Date(value), timeZone));
}

export function zonedInputToIso(value: string, timeZone: string): string | null {
  const parts = parseWall(value);
  if (!parts) return null;
  const guessedMillis = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
  let instant = new Date(guessedMillis - offsetAt(new Date(guessedMillis), timeZone));
  // DST can change the offset between the UTC guess and the intended instant.
  instant = new Date(guessedMillis - offsetAt(instant, timeZone));
  return wallValue(wallPartsAt(instant, timeZone)) === value ? instant.toISOString() : null;
}

export function endOfWallMonth(value: string): string {
  const parts = parseWall(value);
  if (!parts) return "";
  const day = new Date(Date.UTC(parts.year, parts.month, 0)).getUTCDate();
  return wallValue({ ...parts, day, hour: 23, minute: 59 });
}

export function nextWallDay(value: string): string {
  const parts = parseWall(value);
  if (!parts) return "";
  const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + 1, parts.hour, parts.minute));
  return wallValue({
    year: date.getUTCFullYear(), month: date.getUTCMonth() + 1,
    day: date.getUTCDate(), hour: date.getUTCHours(), minute: date.getUTCMinutes(),
  });
}

export function monthTitle(value: string): string {
  const parts = parseWall(value);
  if (!parts) return "";
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(parts.year, parts.month - 1, parts.day)));
}
