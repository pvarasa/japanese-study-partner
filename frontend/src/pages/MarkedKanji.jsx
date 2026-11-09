import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, Brain, Star } from 'lucide-react'
import { Skeleton } from '../components/Skeleton'
import { useKanjiMarks } from '../hooks/useKanjiMarks'
import { usePersistentState } from '../hooks/usePersistentState'
import KanjiPanel from './study/KanjiPanel'

// Unsaved note drafts, kept so a reload mid-edit doesn't lose them.
const DRAFTS_KEY = 'kanji-note-drafts'
const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000

/**
 * The kanji the learner starred on the Read Kanji reveal: a grid to pick one,
 * its full details below (the same panel the reveal uses), a note on why it
 * was marked, and a way into the Marked Kanji drill. The selection lives in
 * the URL (?k=) so it survives a reload.
 */
export default function MarkedKanji() {
  const { marks, error, toggle, isPending, saveNote, reload } = useKanjiMarks()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [actionError, setActionError] = useState(null)

  // Picks up words added to the library since the marks were first loaded.
  useEffect(() => { reload() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const selected = marks?.find(m => m.kanji === params.get('k')) ?? marks?.[0]
  const select = (k) => setParams({ k }, { replace: true })

  const unmark = (k) => {
    setActionError(null)
    toggle(k).catch(err => setActionError(err.message || 'Couldn’t unmark it.'))
  }

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Star size={20} className="text-amber-400" fill="currentColor" />
          Marked kanji
          {marks?.length > 0 && <span className="text-base font-normal text-gray-500">{marks.length}</span>}
        </h1>
        {marks?.length > 0 && (
          <button
            onClick={() => navigate('/study', { state: { startMarked: true } })}
            className="flex items-center gap-1.5 bg-indigo-600 text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-indigo-500"
          >
            <Brain size={16} /> Practice these
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} className="shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={reload} className="text-red-200 underline underline-offset-2 hover:text-white">Retry</button>
        </div>
      )}
      {actionError && <div className="text-sm text-red-300">{actionError}</div>}

      {!marks && !error && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="w-16 h-20 rounded-xl" />)}
          </div>
          <Skeleton className="h-48 rounded-xl" />
        </div>
      )}

      {marks?.length === 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center space-y-2">
          <p className="text-gray-300">No marked kanji yet.</p>
          <p className="text-sm text-gray-500">
            In <Link to="/study" className="text-indigo-400 hover:underline">Study → Read Kanji</Link>, reveal a
            card and tap the <Star size={13} className="inline -mt-0.5 text-amber-400" /> next to a kanji you want to
            come back to.
          </p>
        </div>
      )}

      {marks?.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2">
            {marks.map(m => {
              const active = m.kanji === selected?.kanji
              return (
                <button
                  key={m.kanji}
                  onClick={() => select(m.kanji)}
                  aria-pressed={active}
                  className={`w-16 rounded-xl border px-1 pt-2 pb-1.5 text-center transition-colors ${
                    active
                      ? 'bg-indigo-500/15 border-indigo-500/60'
                      : 'bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/50'
                  }`}
                >
                  <div className="text-3xl leading-none text-gray-100"><span className="jp-text">{m.kanji}</span></div>
                  <div className="mt-1 text-[10px] text-gray-500 truncate">{m.detail?.meaning || ' '}</div>
                </button>
              )
            })}
          </div>

          {selected && (
            <div className="space-y-2">
              <KanjiPanel
                family={{ kanji: selected.kanji, words: selected.words }}
                detail={selected.detail}
                marked
                markPending={isPending(selected.kanji)}
                onToggleMark={() => unmark(selected.kanji)}
              />
              {!selected.detail && (
                <p className="text-xs text-gray-500">
                  Details for this kanji haven’t been generated yet. They appear once a word containing it is revealed in Read Kanji.
                </p>
              )}
              {selected.word_count > selected.words.length && (
                <p className="text-xs text-gray-500">
                  Showing {selected.words.length} of {selected.word_count} library words with <span className="jp-text">{selected.kanji}</span>.
                </p>
              )}
              <NoteEditor key={selected.kanji} kanji={selected.kanji} saved={selected.note} onSave={saveNote} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** Why the kanji was marked, in the learner's words. Saves on blur. */
function NoteEditor({ kanji, saved, onSave }) {
  const [drafts, setDrafts] = usePersistentState(DRAFTS_KEY, {}, { maxAgeMs: DRAFT_MAX_AGE_MS })
  const [status, setStatus] = useState(null) // 'saving' | 'saved' | error message
  const value = drafts[kanji] ?? saved
  const dirty = value !== saved

  const setValue = (v) => {
    setStatus(null)
    setDrafts(d => ({ ...d, [kanji]: v }))
  }

  const save = async () => {
    if (!dirty) return
    setStatus('saving')
    try {
      await onSave(kanji, value)
      setDrafts(d => {
        const rest = { ...d }
        delete rest[kanji]
        return rest
      })
      setStatus('saved')
    } catch (err) {
      setStatus(err.message || 'Couldn’t save the note.')
    }
  }

  return (
    <div>
      <label htmlFor="kanji-note" className="flex justify-between text-xs uppercase tracking-wide text-gray-500 mb-1">
        <span>Note</span>
        <span className="normal-case tracking-normal">
          {status === 'saving' && 'Saving…'}
          {status === 'saved' && <span className="text-green-400">Saved</span>}
          {status && status !== 'saving' && status !== 'saved' && <span className="text-red-300">{status}</span>}
          {!status && dirty && 'Unsaved'}
        </span>
      </label>
      <textarea
        id="kanji-note"
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={save}
        rows={2}
        lang="ja"
        placeholder="Why you marked it, e.g. keeps getting mixed up with 継"
        className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-indigo-500"
      />
    </div>
  )
}
