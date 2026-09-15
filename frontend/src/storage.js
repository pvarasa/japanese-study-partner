// localStorage access that can't take the page down, plus a timestamped
// envelope so a snapshot can expire.
//
// Why state gets persisted at all: switching away from the app on a phone
// routinely costs the page its memory. Mobile browsers discard backgrounded
// tabs and reload them on return, and the Vite dev server reloads the page
// whenever its socket reconnects after the phone slept. Either way, anything
// held only in React state (a study session, a conversation, an unsaved
// import) is gone unless it was written here first.

const ENVELOPE = '__stored'

function storage() {
  // Merely touching window.localStorage throws when site data is blocked.
  try {
    return window.localStorage
  } catch {
    return null
  }
}

/**
 * Read a value written by `saveValue`. Returns `fallback` when nothing is
 * stored, the entry is unreadable, or it's older than `maxAgeMs`.
 *
 * Entries written before the envelope existed are still accepted — a bare
 * JSON value, or a plain string where a string is expected — except where an
 * age limit applies, since their age is unknowable.
 */
export function loadValue(key, fallback, { maxAgeMs } = {}) {
  const store = storage()
  try {
    const raw = store?.getItem(key)
    if (raw == null) return fallback
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch {
      return maxAgeMs == null && typeof fallback === 'string' ? raw : fallback
    }
    if (parsed?.[ENVELOPE] !== 1) return maxAgeMs == null ? parsed : fallback
    if (maxAgeMs != null && !(Date.now() - parsed.savedAt <= maxAgeMs)) {
      store.removeItem(key)
      return fallback
    }
    return parsed.value
  } catch {
    return fallback
  }
}

/** Persist `value` (JSON-serialisable); null/undefined removes the entry. */
export function saveValue(key, value) {
  const store = storage()
  try {
    if (value == null) {
      store?.removeItem(key)
    } else {
      store?.setItem(key, JSON.stringify({ [ENVELOPE]: 1, savedAt: Date.now(), value }))
    }
  } catch {
    // Storage full or unavailable: degrade to in-memory only.
  }
}
