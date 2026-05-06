import { useState, useEffect, useRef } from 'react'
import { api } from '../api'

const isJapanese = (s) => /[぀-ゟ゠-ヿ一-鿿]/.test(s || '')

const SENTENCE_ENDERS = '。！？!?\n'

function containingSentence(fullText, target) {
  if (!fullText || !target) return target || ''
  const idx = fullText.indexOf(target)
  if (idx === -1) return target
  let start = idx
  while (start > 0 && !SENTENCE_ENDERS.includes(fullText[start - 1])) start--
  let end = idx + target.length
  while (end < fullText.length && !SENTENCE_ENDERS.includes(fullText[end])) end++
  if (end < fullText.length) end++
  return fullText.slice(start, end).trim()
}

function selectionTextSkippingRuby(sel, root) {
  if (!sel.rangeCount) return ''
  const range = sel.getRangeAt(0)
  const walkRoot = root && root.contains(range.commonAncestorContainer)
    ? root
    : (range.commonAncestorContainer.nodeType === Node.TEXT_NODE
        ? range.commonAncestorContainer.parentNode
        : range.commonAncestorContainer)
  if (!walkRoot) return ''
  const walker = document.createTreeWalker(walkRoot, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.parentElement && node.parentElement.closest('rt')) return NodeFilter.FILTER_REJECT
      if (!range.intersectsNode(node)) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  let out = ''
  while (walker.nextNode()) {
    const node = walker.currentNode
    let text = node.nodeValue || ''
    if (node === range.startContainer && node === range.endContainer) {
      text = text.substring(range.startOffset, range.endOffset)
    } else if (node === range.startContainer) {
      text = text.substring(range.startOffset)
    } else if (node === range.endContainer) {
      text = text.substring(0, range.endOffset)
    }
    out += text
  }
  return out
}

export default function ReadingText({ text, words = [], className = '' }) {
  const [tokens, setTokens] = useState(null)
  const [openIdx, setOpenIdx] = useState(null)
  const [lookups, setLookups] = useState({})
  const [selPopup, setSelPopup] = useState(null)
  const [selLookups, setSelLookups] = useState({})
  const containerRef = useRef(null)

  useEffect(() => {
    if (!text) return
    setTokens(null)
    setOpenIdx(null)
    setLookups({})
    setSelPopup(null)
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

  useEffect(() => {
    if (!selPopup) return
    const onDocDown = (e) => {
      if (e.target.closest && e.target.closest('[data-sel-popup]')) return
      setSelPopup(null)
    }
    const onScroll = () => setSelPopup(null)
    const t = setTimeout(() => {
      document.addEventListener('mousedown', onDocDown)
      document.addEventListener('touchstart', onDocDown)
      window.addEventListener('scroll', onScroll, true)
      window.addEventListener('resize', onScroll)
    }, 0)
    return () => {
      clearTimeout(t)
      document.removeEventListener('mousedown', onDocDown)
      document.removeEventListener('touchstart', onDocDown)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
    }
  }, [selPopup])

  const handleSelection = () => {
    setTimeout(() => {
      const sel = window.getSelection()
      if (!sel || sel.isCollapsed) return
      const raw = selectionTextSkippingRuby(sel, containerRef.current) || sel.toString()
      const selText = raw.replace(/\s+/g, '').trim()
      if (!selText || selText.length < 2) return
      if (!isJapanese(selText)) return
      const range = sel.getRangeAt(0)
      const container = containerRef.current
      if (!container || !container.contains(range.commonAncestorContainer)) return
      const rect = range.getBoundingClientRect()
      if (!rect.width && !rect.height) return

      setOpenIdx(null)
      const cached = selLookups[selText]
      setSelPopup({
        text: selText,
        rect,
        loading: cached ? false : true,
        meaning: cached?.meaning || '',
        reading: cached?.reading || '',
      })

      if (!cached) {
        api.lookupWord(selText, '', containingSentence(text, selText), true)
          .then(r => {
            const entry = { meaning: r.meaning || '', reading: r.reading || '', error: false }
            setSelLookups(prev => ({ ...prev, [selText]: entry }))
            setSelPopup(prev => prev && prev.text === selText ? { ...prev, loading: false, ...entry } : prev)
          })
          .catch(err => {
            const entry = { meaning: err?.message || 'Translation failed', reading: '', error: true }
            setSelPopup(prev => prev && prev.text === selText ? { ...prev, loading: false, ...entry } : prev)
          })
      }
    }, 0)
  }

  if (!text) return null

  if (!tokens) {
    return <span ref={containerRef} className={`jp-text ${className}`}>{text}</span>
  }

  const handleOpen = (i, t) => {
    setOpenIdx(prev => (prev === i ? null : i))
    const key = t.lemma || t.surface
    if (!t.meaning && !lookups[key] && isJapanese(t.surface)) {
      setLookups(prev => ({ ...prev, [key]: { loading: true } }))
      api.lookupWord(t.surface, t.lemma || '', containingSentence(text, t.surface))
        .then(r => setLookups(prev => ({ ...prev, [key]: { loading: false, meaning: r.meaning, reading: r.reading } })))
        .catch(err => setLookups(prev => ({ ...prev, [key]: { loading: false, meaning: err?.message || '', error: true } })))
    }
  }

  return (
    <span
      ref={containerRef}
      className={`jp-text ${className}`}
      onMouseUp={handleSelection}
      onTouchEnd={handleSelection}
    >
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
      {selPopup && (
        <span
          data-sel-popup
          onClick={e => e.stopPropagation()}
          onMouseDown={e => e.stopPropagation()}
          onTouchStart={e => e.stopPropagation()}
          style={{
            position: 'fixed',
            top: Math.max(8, selPopup.rect.top - 8),
            left: Math.min(
              window.innerWidth - 16,
              Math.max(16, selPopup.rect.left + selPopup.rect.width / 2)
            ),
            transform: 'translate(-50%, -100%)',
            maxWidth: 'min(28rem, calc(100vw - 16px))',
            zIndex: 50,
          }}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 shadow-lg flex flex-col items-center gap-1"
        >
          <span className="jp-text font-medium text-sm text-center break-words">
            {selPopup.text}
            {selPopup.reading && <span className="text-gray-400 ml-2 text-xs">{selPopup.reading}</span>}
          </span>
          <span
            className={`text-center break-words ${selPopup.error ? 'text-amber-300' : 'text-gray-200'}`}
            style={{ fontSize: '0.8rem' }}
          >
            {selPopup.loading ? 'Translating…' : (selPopup.meaning || 'No translation found')}
          </span>
        </span>
      )}
    </span>
  )
}

function WordToken({ surface, reading, dictForm, meaning, loading, open, onOpen }) {
  const hasReading = reading && reading !== surface
  const clickable = isJapanese(surface)

  const inner = hasReading ? (
    <ruby>{surface}<rt style={{ userSelect: 'none' }}>{reading}</rt></ruby>
  ) : (
    surface
  )

  if (!clickable) {
    return <>{inner}</>
  }

  const handleClick = (e) => {
    e.stopPropagation()
    const sel = window.getSelection()
    if (sel && !sel.isCollapsed && sel.toString().trim()) return
    onOpen()
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={handleClick}
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
