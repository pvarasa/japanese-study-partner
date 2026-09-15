import { useMemo, useRef, useState } from 'react'
import { Upload, Link, FileText, Check, X, Loader2 } from 'lucide-react'
import { api } from '../api'
import Badge from '../components/Badge'
import Ruby from '../components/Ruby'
import { usePersistentState } from '../hooks/usePersistentState'

const inputClass = "w-full bg-gray-800 border border-gray-700 text-gray-100 placeholder-gray-500 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"

// Extraction is a slow, paid AI call, so its unsaved result is persisted —
// switching apps while reviewing it shouldn't mean running it again. A day is
// plenty to finish reviewing; after that it's clutter.
const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000
const NO_EXTRACTION = { result: null, selected: [], saved: false }

export default function Ingest() {
  const [input, setInput] = usePersistentState(
    'ingest-input', { tab: 'text', text: '', url: '' }, { maxAgeMs: DRAFT_MAX_AGE_MS }
  )
  // The result and its selection share one entry: `selected` holds indices
  // into `result.items`, so the two must never be restored out of step.
  const [extraction, setExtraction] = usePersistentState(
    'ingest-extraction', NO_EXTRACTION, { maxAgeMs: DRAFT_MAX_AGE_MS }
  )
  // A File can't be serialised; after a reload the PDF has to be re-picked.
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  // Bumped when the input is switched or reset, so an extraction still in
  // flight for the old input doesn't land on top of the new one.
  const requestRef = useRef(0)

  const { tab, text, url } = input
  const { result, saved } = extraction
  const selectedItems = useMemo(() => new Set(extraction.selected), [extraction.selected])
  const setSelected = (indices) => setExtraction(prev => ({ ...prev, selected: [...indices] }))

  const handleIngest = async () => {
    const request = ++requestRef.current
    setLoading(true)
    setError(null)
    setExtraction(NO_EXTRACTION)
    try {
      let res
      if (tab === 'text') {
        res = await api.ingestText(text)
      } else if (tab === 'url') {
        res = await api.ingestUrl(url)
      } else {
        res = await api.ingestPdf(file)
      }
      if (requestRef.current !== request) return
      setExtraction({
        result: res,
        selected: res.items.map((item, i) => [item, i]).filter(([item]) => !item.duplicate).map(([, i]) => i),
        saved: false,
      })
    } catch (err) {
      if (requestRef.current === request) setError(err.message || 'Ingestion failed')
    } finally {
      if (requestRef.current === request) setLoading(false)
    }
  }

  const toggleItem = (idx) => {
    const next = new Set(selectedItems)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    setSelected(next)
  }

  const handleSave = async () => {
    if (!result || selectedItems.size === 0) return
    setSaving(true)
    setError(null)
    const items = result.items
      .filter((_, i) => selectedItems.has(i))
      .map(item => ({
        type: item.type,
        japanese: item.japanese,
        reading: item.reading,
        meaning: item.meaning,
        notes: item.notes,
        example_sentences: item.example_sentences,
        jlpt_level: item.jlpt_level,
        tags: item.tags || [],
      }))
    try {
      await api.saveIngested(result.source_title, tab, tab === 'url' ? url : null, items)
      setExtraction(prev => ({ ...prev, saved: true }))
    } catch (err) {
      setError(err.message)
    }
    setSaving(false)
  }

  const switchTab = (id) => {
    requestRef.current++
    setLoading(false)
    setInput(prev => ({ ...prev, tab: id }))
    setExtraction(NO_EXTRACTION)
    setError(null)
  }

  const tabs = [
    { id: 'text', label: 'Paste Text', icon: FileText },
    { id: 'url', label: 'URL', icon: Link },
    { id: 'pdf', label: 'PDF Upload', icon: Upload },
  ]

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Import Content</h1>

      {/* Tab selector */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => switchTab(t.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-gray-700 shadow text-indigo-400' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Input area */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        {tab === 'text' && (
          <textarea
            value={text}
            onChange={e => setInput(prev => ({ ...prev, text: e.target.value }))}
            rows={6}
            className={`${inputClass} jp-text`}
            placeholder="Paste Japanese text here... Articles, notes, example sentences, etc."
          />
        )}
        {tab === 'url' && (
          <input
            value={url}
            onChange={e => setInput(prev => ({ ...prev, url: e.target.value }))}
            className={inputClass}
            placeholder="https://example.com/japanese-article"
          />
        )}
        {tab === 'pdf' && (
          <div className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center">
            <input
              type="file"
              accept=".pdf"
              onChange={e => setFile(e.target.files[0])}
              className="hidden"
              id="pdf-upload"
            />
            <label htmlFor="pdf-upload" className="cursor-pointer">
              <Upload className="mx-auto text-gray-500 mb-2" size={32} />
              <p className="text-sm text-gray-400">
                {file ? file.name : 'Click to select a PDF file'}
              </p>
            </label>
          </div>
        )}

        <button
          onClick={handleIngest}
          disabled={loading || (tab === 'text' && !text) || (tab === 'url' && !url) || (tab === 'pdf' && !file)}
          className="mt-3 w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-500 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? <><Loader2 className="animate-spin" size={16} /> Analyzing with AI...</> : 'Extract Study Materials'}
        </button>

        {error && <div className="mt-3 text-sm text-red-400 bg-red-500/15 p-3 rounded-lg">{error}</div>}
      </div>

      {/* Results */}
      {result && !saved && (
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">
              Extracted from: {result.source_title}
              <span className="text-sm text-gray-500 ml-2">
                ({result.items.length} items
                {result.items.some(i => i.duplicate) &&
                  `, ${result.items.filter(i => i.duplicate).length} already in your library`}
                )
              </span>
            </h2>
            <div className="flex gap-2">
              <button onClick={() => setSelected(result.items.map((_, i) => i))}
                className="text-sm text-indigo-400 hover:underline">Select all</button>
              <button onClick={() => setSelected([])}
                className="text-sm text-gray-500 hover:underline">Deselect all</button>
            </div>
          </div>

          <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800 max-h-[500px] overflow-y-auto">
            {result.items.map((item, i) => {
              const selected = selectedItems.has(i)
              return (
                <div
                  key={i}
                  onClick={() => toggleItem(i)}
                  className={`px-4 py-3 cursor-pointer transition-colors ${
                    selected ? 'bg-indigo-500/10' : 'hover:bg-gray-800/40'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex items-start gap-3">
                      <div className={`mt-1 w-5 h-5 rounded border flex items-center justify-center shrink-0 ${
                        selected ? 'bg-indigo-600 border-indigo-600' : 'border-gray-600 bg-gray-900'
                      }`}>
                        {selected && <Check size={14} className="text-white" />}
                      </div>
                      <div>
                        <Ruby text={item.japanese} className="font-medium text-lg" />
                        <div className="text-sm text-gray-400">{item.meaning}</div>
                        {item.notes && <div className="text-xs text-gray-500">{item.notes}</div>}
                      </div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      {item.duplicate && <Badge color="amber">already in library</Badge>}
                      <Badge>{item.type}</Badge>
                      {item.jlpt_level && <Badge color="indigo">{item.jlpt_level}</Badge>}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <button
            onClick={handleSave}
            disabled={saving || selectedItems.size === 0}
            className="w-full bg-green-600 text-white py-2.5 rounded-lg font-medium hover:bg-green-500 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {saving ? <><Loader2 className="animate-spin" size={16} /> Saving...</>
              : `Save ${selectedItems.size} items`}
          </button>
        </div>
      )}

      {saved && (
        <div className="text-center py-8 bg-green-500/15 rounded-xl">
          <Check className="mx-auto text-green-400 mb-2" size={32} />
          <p className="text-green-300 font-medium">Items saved successfully!</p>
          <button
            onClick={() => {
              setExtraction(NO_EXTRACTION)
              setInput(prev => ({ ...prev, text: '', url: '' }))
              setFile(null)
            }}
            className="mt-3 text-sm text-indigo-400 hover:underline"
          >
            Import more content
          </button>
        </div>
      )}
    </div>
  )
}
