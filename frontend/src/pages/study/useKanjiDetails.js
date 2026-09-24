import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'

// Item id → in-flight or settled request. Module-level so the prefetch for the
// next card and that card's own fetch share one request. Failures are evicted
// so a retry actually goes back to the server.
const cache = new Map()

function load(itemId) {
  if (!cache.has(itemId)) {
    cache.set(itemId, api.getItemKanji(itemId).catch(err => {
      cache.delete(itemId)
      throw err
    }))
  }
  return cache.get(itemId)
}

/**
 * Per-kanji details for the reading drill, fetched as soon as the card is
 * shown (so it's usually ready by the reveal) and the next card's in the
 * background. Returns `{ details, error, retry }`; `details` is null while
 * loading and otherwise maps kanji → detail.
 */
export function useKanjiDetails(itemId, nextItemId) {
  const [state, setState] = useState({ itemId: null, details: null, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    load(itemId)
      .then(list => {
        if (live) setState({ itemId, details: Object.fromEntries(list.map(d => [d.kanji, d])), error: null })
      })
      .catch(err => {
        if (live) setState({ itemId, details: null, error: err.message || 'Couldn’t load kanji details.' })
      })
    return () => { live = false }
  }, [itemId, attempt])

  // Warm the next card; its errors surface (and retry) when it's shown.
  useEffect(() => {
    if (nextItemId != null) load(nextItemId).catch(() => {})
  }, [nextItemId])

  const retry = useCallback(() => {
    setState({ itemId, details: null, error: null })
    setAttempt(a => a + 1)
  }, [itemId])

  // Ignore a previous card's result until this card's arrives.
  const current = state.itemId === itemId
  return {
    details: current ? state.details : null,
    error: current ? state.error : null,
    retry,
  }
}
