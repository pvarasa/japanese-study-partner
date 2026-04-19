import { useState, useEffect, useRef } from 'react'
import { api } from '../api'

const cache = new Map()
let pending = new Map()
let flushTimer = null

function flush() {
  if (pending.size === 0) return
  const batch = new Map(pending)
  pending = new Map()
  flushTimer = null

  const texts = [...batch.keys()]
  api.furigana(texts).then(({ results }) => {
    texts.forEach((t, i) => {
      cache.set(t, results[i])
      batch.get(t).forEach(cb => cb(results[i]))
    })
  }).catch(() => {
    // On error, just show without furigana
    texts.forEach(t => batch.get(t).forEach(cb => cb(null)))
  })
}

function requestFurigana(text, callback) {
  if (cache.has(text)) {
    callback(cache.get(text))
    return
  }
  if (!pending.has(text)) pending.set(text, [])
  pending.get(text).push(callback)
  if (!flushTimer) flushTimer = setTimeout(flush, 50)
}

export default function Ruby({ text, className = '' }) {
  const [html, setHtml] = useState(null)

  useEffect(() => {
    if (!text) return
    setHtml(null)
    requestFurigana(text, (result) => {
      if (result !== null) setHtml(result)
    })
  }, [text])

  if (!text) return null

  if (html) {
    return <span className={`jp-text ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
  }
  return <span className={`jp-text ${className}`}>{text}</span>
}
