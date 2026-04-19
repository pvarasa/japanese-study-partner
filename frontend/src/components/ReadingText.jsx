import { useState, useEffect } from 'react'
import { api } from '../api'

const isJapanese = (s) => /[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]/.test(s || '')

export default function ReadingText({ text, words = [], className = '' }) {
  const [tokens, setTokens] = useState(null)
  const [openIdx, setOpenIdx] = useState(null)
  const [lookups, setLookups] = useState({})

  useEffect(() => {
    if (!text) return
    setTokens(null)
    setOpenIdx(null)
    setLookups({})
    api.tokenize(text, words).then(r => setTokens(r.tokens)).catch(() => {})
  }, [text])

  useEffect(() => {
    if (openIdx === null) return
    const onDocClick = () => setOpenIdx(null)
    const t = setTimeout(() => document.addEventListener('click', onDocClick), 0)
    return () => {
      clearTimeout(t)
      document.removeEventListener('click', onDocClick)
    }
  }, [openIdx])

  if (!text) return null

  if (!tokens) {
    return <span className={`jp-text ${className}`}>{text}</span>
  }

  const handleOpen = (i, t) => {
    setOpenIdx(prev => (prev === i ? null : i))
    const key = t.lemma || t.surface
    if (!t.meaning && !lookups[key] && isJapanese(t.surface)) {
      setLookups(prev => ({ ...prev, [key]: { loading: true } }))
      api.lookupWord(t.surface, t.lemma || '', text)
        .then(r => setLookups(prev => ({ ...prev, [key]: { loading: false, meaning: r.meaning, reading: r.reading } })))
        .catch(() => setLookups(prev => ({ ...prev, [key]: { loading: false, meaning: '' } })))
    }
  }

  return (
    <span className={`jp-text ${className}`}>
      {tokens.map((t, i) => {
        const key = t.lemma || t.surface
        const looked = lookups[key]
        const effectiveMeaning = t.meaning || looked?.meaning || ''
        const loading = looked?.loading
        const dictForm = t.lemma && t.lemma !== t.surface ? t.lemma : ''
        return (
          <WordToken
            key={i}
            surface={t.surface}
            reading={t.reading || (looked?.reading && looked.reading !== t.surface ? looked.reading : '')}
            dictForm={dictForm}
            meaning={effectiveMeaning}
            loading={loading}
            open={openIdx === i}
            onOpen={() => handleOpen(i, t)}
          />
        )
      })}
    </span>
  )
}

function WordToken({ surface, reading, dictForm, meaning, loading, open, onOpen }) {
  const hasReading = reading && reading !== surface
  const clickable = isJapanese(surface)

  const inner = hasReading ? (
    <ruby>{surface}<rt>{reading}</rt></ruby>
  ) : (
    surface
  )

  if (!clickable) {
    return <>{inner}</>
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={e => { e.stopPropagation(); onOpen() }}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
      className={`relative cursor-pointer rounded px-0.5 transition-colors ${open ? 'bg-indigo-500/25' : 'hover:bg-indigo-500/15'}`}
      style={{ borderBottom: '1px dashed rgba(129,140,248,0.45)' }}
    >
      {inner}
      {open && (
        <span
          onClick={e => e.stopPropagation()}
          className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 whitespace-nowrap z-50 shadow-lg flex flex-col items-center gap-0.5"
        >
          <span className="jp-text font-medium text-sm">
            {dictForm || surface}
            {reading && <span className="text-gray-400 ml-2 text-xs">{reading}</span>}
          </span>
          <span className="text-gray-200" style={{ fontSize: '0.8rem' }}>
            {loading ? 'Looking up…' : (meaning || 'No meaning found')}
          </span>
        </span>
      )}
    </span>
  )
}
