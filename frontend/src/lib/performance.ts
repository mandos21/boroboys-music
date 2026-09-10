const prefix = "borocrew:";

function isEnabled() {
  return import.meta.env.DEV || import.meta.env.VITE_PERFORMANCE_MARKS === "true";
}

/**
 * Leave inspectable User Timing entries without coupling normal application
 * behavior to analytics. Enable the same marks in a deployed build with
 * VITE_PERFORMANCE_MARKS=true when profiling a real stack.
 */
export function markPerformance(name: string, start?: string) {
  if (!isEnabled() || typeof performance === "undefined") return;
  const mark = `${prefix}${name}`;
  performance.mark(mark);
  if (!start) return;
  const startMark = `${prefix}${start}`;
  if (!performance.getEntriesByName(startMark).some((entry) => entry.entryType === "mark")) {
    return;
  }
  const measure = `${prefix}${start}->${name}`;
  performance.clearMeasures(measure);
  performance.measure(measure, startMark, mark);
}
