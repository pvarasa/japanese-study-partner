import { useState, useEffect } from 'react'

// useState that mirrors its value to localStorage, so generated content
// survives a full page reload. Mobile browsers commonly discard a
// backgrounded tab and reload it fresh when you switch back, which would
// otherwise wipe in-memory React state (e.g. a generated reading passage).
export function usePersistentState(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const stored = localStorage.getItem(key)
      return stored !== null ? JSON.parse(stored) : initialValue
    } catch {
      return initialValue
    }
  })

  useEffect(() => {
    try {
      if (value === undefined || value === null) {
        localStorage.removeItem(key)
      } else {
        localStorage.setItem(key, JSON.stringify(value))
      }
    } catch {
      // storage unavailable or full — degrade to in-memory only
    }
  }, [key, value])

  return [value, setValue]
}
