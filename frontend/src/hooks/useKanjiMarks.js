import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { api } from '../api'

// One store for the whole app, so a star toggled on one drill card shows on
// the next card with the same kanji (whose details were prefetched before the
// toggle) and on the Kanji page, without refetching per card.
//
// `marks` is null until the first load, then an array of MarkedKanji (newest
// first). `pending` holds kanji whose toggle is in flight, so a double tap
// can't send mark and unmark out of order.
let state = { marks: null, error: null, pending: new Set() }
let loading = null
const listeners = new Set()

function set(update) {
  state = { ...state, ...update }
  listeners.forEach(l => l())
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function load({ force = false } = {}) {
  if (loading || (state.marks && !force)) return loading
  loading = api.getKanjiMarks()
    .then(marks => set({ marks, error: null }))
    .catch(err => set({ error: err.message || 'Couldn’t load your marked kanji.' }))
    .finally(() => { loading = null })
  return loading
}

const withPending = (kanji, on) => {
  const pending = new Set(state.pending)
  if (on) pending.add(kanji)
  else pending.delete(kanji)
  return pending
}

/** Mark or unmark a kanji. Optimistic; rolls back and rethrows on failure. */
async function toggle(kanji) {
  if (state.pending.has(kanji)) return
  // A list arriving after the toggle would overwrite it, so settle that first.
  if (!state.marks) await load()
  if (state.pending.has(kanji)) return
  const before = state.marks || []
  const marking = !before.some(m => m.kanji === kanji)
  set({
    pending: withPending(kanji, true),
    marks: marking
      ? [{ kanji, note: '', detail: null, words: [], word_count: 0 }, ...before]
      : before.filter(m => m.kanji !== kanji),
  })
  try {
    if (marking) {
      const saved = await api.markKanji(kanji)
      set({ marks: (state.marks || []).map(m => (m.kanji === kanji ? saved : m)) })
    } else {
      await api.unmarkKanji(kanji)
    }
  } catch (err) {
    set({ marks: before })
    throw err
  } finally {
    set({ pending: withPending(kanji, false) })
  }
}

async function saveNote(kanji, note) {
  const saved = await api.markKanji(kanji, note)
  set({ marks: (state.marks || []).map(m => (m.kanji === kanji ? saved : m)) })
}

/**
 * The learner's marked kanji. Loads once per app session; `reload` refetches
 * (the Kanji page does on mount, to pick up words added since).
 */
export function useKanjiMarks() {
  const snap = useSyncExternalStore(subscribe, () => state)
  useEffect(() => { load() }, [])
  const isMarked = useCallback(k => !!snap.marks?.some(m => m.kanji === k), [snap.marks])
  return {
    marks: snap.marks,
    error: snap.error,
    isMarked,
    isPending: k => snap.pending.has(k),
    toggle,
    saveNote,
    reload: () => load({ force: true }),
  }
}
