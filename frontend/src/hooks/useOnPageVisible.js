import { useEffect, useRef } from 'react'

/**
 * Calls `callback` when the tab becomes visible again after being hidden for
 * at least `minHiddenMs` — i.e. the learner switched apps or tabs and came
 * back. For refreshing data that may have gone stale meanwhile (due counts,
 * a setting changed on another device), without refetching on every quick
 * glance away.
 *
 * `callback` is read from a ref, so passing a fresh closure each render
 * doesn't re-subscribe the listener.
 */
export function useOnPageVisible(callback, { minHiddenMs = 60_000 } = {}) {
  const callbackRef = useRef(callback)
  useEffect(() => {
    callbackRef.current = callback
  })

  useEffect(() => {
    let hiddenAt = document.hidden ? Date.now() : null
    const onChange = () => {
      if (document.hidden) {
        hiddenAt = Date.now()
      } else if (hiddenAt != null) {
        const away = Date.now() - hiddenAt
        hiddenAt = null
        if (away >= minHiddenMs) callbackRef.current()
      }
    }
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [minHiddenMs])
}
