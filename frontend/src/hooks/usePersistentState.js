import { useState, useEffect } from 'react'
import { loadValue, saveValue } from '../storage'

// useState that mirrors its value to localStorage, so it survives the page
// being reloaded out from under the user (see storage.js for why that happens
// so often on mobile). `maxAgeMs` drops a value that hasn't been written for
// that long, for state that shouldn't resurface the next day.
export function usePersistentState(key, initialValue, { maxAgeMs } = {}) {
  const [value, setValue] = useState(() => loadValue(key, initialValue, { maxAgeMs }))

  useEffect(() => {
    saveValue(key, value)
  }, [key, value])

  return [value, setValue]
}
