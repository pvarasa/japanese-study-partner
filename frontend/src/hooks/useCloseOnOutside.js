import { useEffect, useRef } from 'react'

/**
 * Closes a popup/dropdown on outside interaction (registered a tick late so
 * the click/tap that opened it doesn't immediately close it again), and
 * optionally on scroll/resize for popups positioned relative to something
 * that just moved (e.g. a text selection).
 *
 * `onClose` and `options` are read from refs rather than the effect's
 * dependency array, so passing a fresh arrow function each render doesn't
 * tear down and re-install the listeners — the effect only re-runs when
 * `active` itself flips.
 */
export function useCloseOnOutside(active, onClose, options = {}) {
  const onCloseRef = useRef(onClose)
  const optionsRef = useRef(options)
  // Refs are synced after render (not mutated during it — React flags that as
  // impure) so the listeners below always call the latest closure.
  useEffect(() => {
    onCloseRef.current = onClose
    optionsRef.current = options
  })

  useEffect(() => {
    if (!active) return
    const { events = ['click'], ignoreSelector, closeOnViewportChange = false } = optionsRef.current

    const handler = (e) => {
      if (ignoreSelector && e.target.closest && e.target.closest(ignoreSelector)) return
      onCloseRef.current()
    }
    const onViewportChange = () => onCloseRef.current()

    const t = setTimeout(() => {
      events.forEach(ev => document.addEventListener(ev, handler))
      if (closeOnViewportChange) {
        window.addEventListener('scroll', onViewportChange, true)
        window.addEventListener('resize', onViewportChange)
      }
    }, 0)
    return () => {
      clearTimeout(t)
      events.forEach(ev => document.removeEventListener(ev, handler))
      if (closeOnViewportChange) {
        window.removeEventListener('scroll', onViewportChange, true)
        window.removeEventListener('resize', onViewportChange)
      }
    }
  }, [active])
}
