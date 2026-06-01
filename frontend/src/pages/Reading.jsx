import { useState } from 'react'
import { BookOpen, Loader2, Eye, EyeOff, Plus, Check } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
import ReadingText from '../components/ReadingText'
import LevelBadge from '../components/LevelBadge'
import { Skeleton, SkeletonLine } from '../components/Skeleton'
import { useLevel } from '../context/LevelContext'
import { usePersistentState } from '../hooks/usePersistentState'

export default function Reading() {
  const { jlptLevel } = useLevel()
  // Persisted so a generated passage survives a tab reload (mobile browsers
  // discard backgrounded tabs and reload them fresh on return).
  const [prompt, setPrompt] = usePersistentState('reading-prompt', '')
  const [passage, setPassage] = usePersistentState('reading-passage', null)
  const [savedWords, setSavedWords] = usePersistentState('reading-saved-words', [])
  const [loading, setLoading] = useState(false)
  const [showTranslation, setShowTranslation] = useState(false)
  const [showWordMeanings, setShowWordMeanings] = useState(false)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(null)

  const generate = async () => {
    setLoading(true)
    setError(null)
    setPassage(null)
    setShowTranslation(false)
    setShowWordMeanings(false)
    setSavedWords([])
    try {
      const res = await api.generateReading(prompt || null)
      setPassage(res)
    } catch (err) {
      setError(err.message || 'Failed to generate passage')
    }
    setLoading(false)
  }

  const saveWord = async (word) => {
    setSaving(word.japanese)
    try {
      await api.createItem({
        type: 'word',
        japanese: word.japanese,
        reading: word.reading,
        meaning: word.meaning,
        jlpt_level: jlptLevel,
        tags: ['from-reading'],
      })
      setSavedWords(prev => prev.includes(word.japanese) ? prev : [...prev, word.japanese])
    } catch {
      // ignore duplicates
      setSavedWords(prev => prev.includes(word.japanese) ? prev : [...prev, word.japanese])
    }
    setSaving(null)
  }

  const libraryWords = passage?.words.filter(w => w.in_library) || []
  const newWords = passage?.words.filter(w => !w.in_library) || []

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Reading Practice</h1>
        <LevelBadge />
      </div>

      {/* Prompt input */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-3">
        <input
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !loading && generate()}
          className="w-full bg-gray-800 border border-gray-700 text-gray-100 placeholder-gray-500 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
          placeholder="Optional: guide the topic (e.g. 'daily commute', 'cooking', 'weekend plans')"
        />
        <button
          onClick={generate}
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-500 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <><Loader2 className="animate-spin" size={16} /> Generating passage...</>
          ) : (
            <><BookOpen size={16} /> Generate Reading</>
          )}
        </button>
        {error && <div className="text-sm text-red-400 bg-red-500/15 p-3 rounded-lg">{error}</div>}
      </div>

      {/* Loading skeleton */}
      {loading && !passage && (
        <div className="space-y-4">
          <Skeleton className="h-6 w-1/3" />
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 sm:p-8 space-y-3">
            <SkeletonLine width="95%" className="h-5" />
            <SkeletonLine width="88%" className="h-5" />
            <SkeletonLine width="92%" className="h-5" />
            <SkeletonLine width="70%" className="h-5" />
          </div>
        </div>
      )}

      {/* Passage */}
      {passage && (
        <div className="space-y-4">
          {/* Title */}
          <h2 className="text-lg font-semibold">
            <Ruby text={passage.title} />
          </h2>

          {/* Reading text */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 sm:p-8">
            <div className="text-xl">
              <ReadingText text={passage.text} words={passage.words} className="jp-reading" />
            </div>
          </div>

          {/* Translation toggle */}
          <button
            onClick={() => setShowTranslation(!showTranslation)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200"
          >
            {showTranslation ? <EyeOff size={14} /> : <Eye size={14} />}
            {showTranslation ? 'Hide' : 'Show'} translation
          </button>
          {showTranslation && (
            <div className="bg-gray-900/50 rounded-lg border border-gray-800 p-4 text-gray-400 text-sm">
              {passage.translation}
            </div>
          )}

          {/* Word meanings toggle */}
          <button
            onClick={() => setShowWordMeanings(!showWordMeanings)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200"
          >
            {showWordMeanings ? <EyeOff size={14} /> : <Eye size={14} />}
            {showWordMeanings ? 'Hide' : 'Show'} word list
          </button>

          {showWordMeanings && (
            <div className="space-y-3">
              {/* Library words */}
              {libraryWords.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">From your library</div>
                  <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
                    {libraryWords.map((w, i) => (
                      <div key={i} className="px-4 py-2 flex justify-between items-center">
                        <div>
                          <Ruby text={w.japanese} className="font-medium" />
                          <span className="text-sm text-gray-500 ml-2">{w.reading}</span>
                        </div>
                        <span className="text-sm text-gray-400">{w.meaning}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* New words */}
              {newWords.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-indigo-400 uppercase tracking-wider mb-2">New words</div>
                  <div className="bg-gray-900 rounded-xl border border-indigo-500/20 divide-y divide-gray-800">
                    {newWords.map((w, i) => (
                      <div key={i} className="px-4 py-2 flex justify-between items-center">
                        <div>
                          <Ruby text={w.japanese} className="font-medium" />
                          <span className="text-sm text-gray-500 ml-2">{w.reading}</span>
                          <span className="text-sm text-gray-400 ml-3">{w.meaning}</span>
                        </div>
                        {savedWords.includes(w.japanese) ? (
                          <span className="text-green-400"><Check size={16} /></span>
                        ) : (
                          <button
                            onClick={() => saveWord(w)}
                            disabled={saving === w.japanese}
                            className="text-indigo-400 hover:text-indigo-300 p-1"
                            title="Add to library"
                          >
                            {saving === w.japanese ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Generate another */}
          <button
            onClick={generate}
            disabled={loading}
            className="w-full border border-gray-700 text-gray-300 py-2 rounded-lg hover:bg-gray-800 text-sm"
          >
            Generate another passage
          </button>
        </div>
      )}
    </div>
  )
}
