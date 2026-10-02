/** "Alice", "Alice and Bob", or "Alice, Bob and Carol" - never an Oxford comma. */
export function joinNames(names: string[]) {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
