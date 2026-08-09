/** Shared display formatting. */

/**
 * Format a 0–1 rate from the API as a whole percentage.
 *
 * `pass_rate` / `recall_rate` are derived server-side (see app/srs.py) so every
 * view reports the same definitions; this only handles presentation.
 */
export const pct = (rate) => `${Math.round(rate * 100)}%`
