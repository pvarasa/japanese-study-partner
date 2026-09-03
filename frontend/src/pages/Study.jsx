import { useState } from 'react'
import { RotateCcw, ArrowRight, Zap, CheckCircle, X, Sparkles, Loader2, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
import LevelBadge from '../components/LevelBadge'
import SpeakButton from '../components/SpeakButton'
import { Skeleton, SkeletonLine } from '../components/Skeleton'

const MODES = [
  { id: 'flashcard_jp', label: 'JP → EN', desc: 'See Japanese, recall English' },
  { id: 'flashcard_en', label: 'EN → JP', desc: 'See English, recall Japanese' },
  { id: 'cloze', label: 'Cloze', desc: 'Recall the word in its own sentence' },
  { id: 'fill_blank', label: 'Fill Blank', desc: 'Complete the sentence' },
  { id: 'sentence_build', label: 'Build Sentence', desc: 'Translate to Japanese' },
  { id: 'grammar_drill', label: 'Grammar Drill', desc: 'Choose the correct usage' },
]

// Modes that fetch a question per item rather than showing a plain flashcard.
// Cloze goes through the same endpoint but is built from the item's stored
// example sentences, so it costs no AI call and returns instantly.
const GENERATED_MODES = ['cloze', 'fill_blank', 'sentence_build', 'grammar_drill']

// Fallback when the generate request fails without a server-provided detail.
const QUESTION_ERROR = 'Failed to load this question. Please try again.'
// Fallback when submitting a review rating fails.
const RATE_ERROR = 'Failed to save your review. Please try again.'

// The placeholder the server blanks the target word out with. Must match
// BLANK in backend/app/cloze.py — it's what turns a cloze prompt back into a
// full sentence for the read-aloud button.
const CLOZE_BLANK = '＿＿＿'

/** Compare a typed answer against the accepted spellings. */
function isAnswerAccepted(userAnswer, question) {
  const given = (userAnswer || '').trim()
  if (!given) return false
  const accepted = question.accepted?.length ? question.accepted : [question.answer]
  return accepted.some(a => a.trim() === given)
}

// How many stored examples the reveal shows. Items are generated with
// EXAMPLES_PER_ITEM (app/enrich.py) of them, but older ingested rows can carry
// three or four — cap the card rather than letting its height vary per item.
const SHOWN_EXAMPLES = 2

// `example_sentences` is a JSON string in a text column, authored by the LLM at
// ingest time and never validated as parseable. A malformed value used to throw
// during render and blank the page, so degrade to "no examples" instead.
function parseExamples(raw) {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(e => e && typeof e.japanese === 'string')
  } catch {
    return []
  }
}

export default function Study() {
  const [mode, setMode] = useState(null)
  // Practice pulls extra reps from the whole library instead of just due
  // items, and reviewing them doesn't touch SRS scheduling. Toggled on the
  // mode-selection screen, then fixed for the life of the session.
  const [practice, setPractice] = useState(false)
  const [items, setItems] = useState([])
  const [current, setCurrent] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [sessionStats, setSessionStats] = useState({ reviewed: 0, correct: 0 })
  const [question, setQuestion] = useState(null)
  const [userAnswer, setUserAnswer] = useState('')
  const [answerChecked, setAnswerChecked] = useState(false)
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [generatedExample, setGeneratedExample] = useState(null)
  const [generatingExample, setGeneratingExample] = useState(false)
  const [translationRevealed, setTranslationRevealed] = useState(false)
  const [hintsRevealed, setHintsRevealed] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [evaluation, setEvaluation] = useState(null)
  const [error, setError] = useState(null)

  /**
   * Fetch the question for the first item at or after `from` that has one.
   *
   * Cloze can legitimately produce nothing for an item (no stored example
   * actually uses the word), which the server reports as a 422. Skip those
   * instead of stalling the session on an error the learner can't act on.
   */
  const loadQuestionFrom = async (list, from, m) => {
    for (let i = from; i < list.length; i++) {
      try {
        return { index: i, question: await api.generateQuestion(list[i].id, m) }
      } catch (err) {
        if (err.status === 422) continue
        throw err
      }
    }
    return null
  }

  const startStudy = async (m) => {
    setMode(m)
    setLoading(true)
    setError(null)
    try {
      const due = practice
        ? await api.getPracticeItems({ limit: 20 })
        : await api.getDueItems({ limit: 20 })
      if (due.length === 0) {
        setItems([])
        setDone(true)
        setLoading(false)
        return
      }
      setItems(due)
      setCurrent(0)
      setRevealed(false)
      setUserAnswer('')
      setAnswerChecked(false)
      setGeneratedExample(null)
      setGeneratingExample(false)
      setTranslationRevealed(false)
      setHintsRevealed(false)
      setEvaluating(false)
      setEvaluation(null)
      setDone(false)
      setSessionStats({ reviewed: 0, correct: 0 })
      // Distinct mode label keeps practice reps out of accuracy_today and the
      // retention chart (see GRADED_MODES in routers/study.py) while still
      // counting toward studied-today and the streak, same as converse turns.
      const sess = await api.startSession(practice ? `practice_${m}` : m)
      setSessionId(sess.session_id)

      if (GENERATED_MODES.includes(m)) {
        const found = await loadQuestionFrom(due, 0, m)
        if (!found) {
          // Nothing in this batch can produce a question for this mode.
          setDone(true)
          setLoading(false)
          return
        }
        setCurrent(found.index)
        setQuestion(found.question)
      }
    } catch (err) {
      setError(err.message || QUESTION_ERROR)
    }
    setLoading(false)
  }

  // Re-generate the question for the current item (used by the error retry).
  const retryQuestion = async () => {
    setError(null)
    setLoading(true)
    try {
      const q = await api.generateQuestion(items[current].id, mode)
      setQuestion(q)
    } catch (err) {
      setError(err.message || QUESTION_ERROR)
    }
    setLoading(false)
  }

  /** Close the session without counts — progress is already recorded per review. */
  const finishSession = async () => {
    if (!sessionId) return
    setSessionId(null)
    try {
      await api.endSession(sessionId)
    } catch { /* ignore — the reviews themselves are already recorded */ }
  }

  const exitStudy = () => {
    finishSession()
    setMode(null)
    setDone(false)
  }

  const handleRate = async (rating) => {
    const item = items[current]
    setError(null)
    try {
      // Passing the session id records this review against the session
      // server-side, so quitting part-way keeps what was already done.
      await api.reviewItem(item.id, rating, sessionId, practice)
    } catch (err) {
      // Keep the card in place so the user can retry the same rating.
      setError(err.message || RATE_ERROR)
      return
    }
    setSessionStats({
      reviewed: sessionStats.reviewed + 1,
      // Strict: only a clean recall counts. "Hard" means it was dredged up.
      correct: sessionStats.correct + (rating === 'good' ? 1 : 0),
    })

    // Clear everything the previous card left behind.
    const resetCard = () => {
      setRevealed(false)
      setQuestion(null)
      setUserAnswer('')
      setAnswerChecked(false)
      setGeneratedExample(null)
      setGeneratingExample(false)
      setTranslationRevealed(false)
      setHintsRevealed(false)
      setEvaluating(false)
      setEvaluation(null)
      setError(null)
    }

    if (current + 1 >= items.length) {
      await finishSession()
      setDone(true)
      return
    }

    resetCard()
    setCurrent(current + 1)

    if (!GENERATED_MODES.includes(mode)) return

    // Advance optimistically above, then correct forward once the fetch lands:
    // loadQuestionFrom skips items that can't produce a question, so its result
    // is the real next index. Leaving `current` behind during the await would
    // point the error card's retry at the item just answered.
    setLoading(true)
    try {
      const found = await loadQuestionFrom(items, current + 1, mode)
      if (found) {
        setCurrent(found.index)
        setQuestion(found.question)
      } else {
        // Every remaining item was skipped — nothing left to ask.
        await finishSession()
        setDone(true)
      }
    } catch (err) {
      setError(err.message || QUESTION_ERROR)
    }
    setLoading(false)
  }

  const checkAnswer = async () => {
    setAnswerChecked(true)
    setRevealed(true)
    if (mode === 'sentence_build') {
      setEvaluating(true)
      try {
        const result = await api.evaluateAnswer(userAnswer, question.answer, question.prompt)
        setEvaluation(result)
      } catch (err) {
        setEvaluation({ verdict: 'incorrect', feedback: err.message || 'Could not evaluate answer.', corrected: null })
      }
      setEvaluating(false)
    }
  }

  // Mode selection
  if (!mode) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Study</h1>
          <LevelBadge />
        </div>
        <div className="space-y-1.5">
          <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
            <button
              onClick={() => setPractice(false)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                !practice ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Due Reviews
            </button>
            <button
              onClick={() => setPractice(true)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                practice ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Practice
            </button>
          </div>
          {practice && (
            <p className="text-xs text-gray-500">
              Extra reps from your whole library. Doesn't affect scheduling or leech tracking.
            </p>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {MODES.map(m => (
            <button
              key={m.id}
              onClick={() => startStudy(m.id)}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-left hover:border-indigo-500/50 hover:bg-gray-800/50 transition-all"
            >
              <div className="font-medium text-lg text-gray-100">{m.label}</div>
              <div className="text-sm text-gray-500">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="max-w-lg mx-auto space-y-4">
        <div className="flex justify-between">
          <SkeletonLine width="60px" />
          <SkeletonLine width="40px" />
        </div>
        <Skeleton className="h-64 rounded-2xl" />
        <div className="grid grid-cols-3 gap-2">
          <Skeleton className="h-12 rounded-xl" />
          <Skeleton className="h-12 rounded-xl" />
          <Skeleton className="h-12 rounded-xl" />
        </div>
      </div>
    )
  }

  // Session complete
  if (done) {
    const accuracy = sessionStats.reviewed > 0
      ? Math.round(sessionStats.correct / sessionStats.reviewed * 100)
      : 0
    return (
      <div className="text-center py-12 space-y-4">
        <CheckCircle className="mx-auto text-green-400" size={48} />
        <h2 className="text-2xl font-bold">
          {items.length === 0
            ? (practice ? 'Nothing to practice yet' : 'All caught up!')
            : 'Session Complete!'}
        </h2>
        {sessionStats.reviewed > 0 && (
          <div className="text-gray-400">
            <p>Reviewed: {sessionStats.reviewed} items</p>
            <p>Accuracy: {accuracy}%</p>
          </div>
        )}
        <div className="flex gap-3 justify-center">
          <button onClick={exitStudy}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-500">
            Back to modes
          </button>
          <button onClick={() => startStudy(mode)}
            className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-800">
            Study again
          </button>
        </div>
      </div>
    )
  }

  const item = items[current]
  const progress = `${current + 1} / ${items.length}`
  const examples = parseExamples(item.example_sentences)

  const ratingButtons = (
    <div className="space-y-2">
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} /> {error}
        </div>
      )}
      <div className="grid grid-cols-3 gap-2">
      <button onClick={() => handleRate('again')}
        className="bg-red-500/15 text-red-400 border border-red-500/30 py-3 rounded-xl font-medium hover:bg-red-500/25 transition-colors">
        <RotateCcw className="inline mr-1" size={16} /> Again
      </button>
      <button onClick={() => handleRate('hard')}
        className="bg-orange-500/15 text-orange-400 border border-orange-500/30 py-3 rounded-xl font-medium hover:bg-orange-500/25 transition-colors">
        <Zap className="inline mr-1" size={16} /> Hard
      </button>
      <button onClick={() => handleRate('good')}
        className="bg-green-500/15 text-green-400 border border-green-500/30 py-3 rounded-xl font-medium hover:bg-green-500/25 transition-colors">
        <ArrowRight className="inline mr-1" size={16} /> Good
      </button>
      </div>
    </div>
  )

  // AI-question modes (fill_blank, grammar_drill, sentence_build) have an
  // objectively correct answer, so the SRS rating is derived from correctness
  // instead of asking the learner to self-grade.
  const derivedRating = mode === 'sentence_build'
    ? (evaluation?.verdict === 'correct' ? 'good' : evaluation?.verdict === 'partial' ? 'hard' : 'again')
    : (question && isAnswerAccepted(userAnswer, question) ? 'good' : 'again')

  const RATING_LABEL = { good: 'Good', hard: 'Hard', again: 'Again' }
  const RATING_COLOR = { good: 'text-green-400', hard: 'text-orange-400', again: 'text-red-400' }

  const continueControl = (
    <div className="space-y-2">
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} /> {error}
        </div>
      )}
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-gray-500">
          {practice ? 'Rated' : 'Scheduled as'}{' '}
          <span className={RATING_COLOR[derivedRating]}>{RATING_LABEL[derivedRating]}</span>
        </span>
        <button
          onClick={() => handleRate(derivedRating)}
          className="bg-indigo-600 text-white px-6 py-2.5 rounded-xl font-medium hover:bg-indigo-500 flex items-center gap-1.5"
        >
          Next <ArrowRight size={16} />
        </button>
      </div>
    </div>
  )

  // Flashcard modes
  if (mode === 'flashcard_jp' || mode === 'flashcard_en') {
    const isJpToEn = mode === 'flashcard_jp'
    return (
      <div className="max-w-lg mx-auto space-y-4">
        <div className="flex justify-between items-center text-sm text-gray-500">
          <span>{progress}</span>
          <button onClick={exitStudy} className="text-gray-500 hover:text-gray-300">Exit</button>
        </div>

        {/* Card */}
        <div
          className="bg-gray-900 rounded-2xl border border-gray-800 p-8 text-center min-h-[250px] flex flex-col justify-center cursor-pointer"
          onClick={() => setRevealed(true)}
        >
          {isJpToEn ? (
            <div className="flex items-center justify-center gap-1 mb-2">
              <Ruby text={item.japanese} className="text-3xl font-medium" />
              <SpeakButton text={item.japanese} size={17} />
            </div>
          ) : (
            <div className="text-xl font-medium mb-2">{item.meaning}</div>
          )}

          {!revealed && (
            <div className="text-sm text-gray-600 mt-4">Tap to reveal</div>
          )}

          {revealed && (
            <div className="mt-4 pt-4 border-t border-gray-800">
              {isJpToEn ? (
                <div className="text-lg font-medium">{item.meaning}</div>
              ) : (
                // EN → JP: the speaker only appears after the reveal, since
                // hearing the word before answering would give it away.
                <div className="flex items-center justify-center gap-1">
                  <Ruby text={item.japanese} className="text-2xl font-medium" />
                  <SpeakButton text={item.japanese} size={16} />
                </div>
              )}
              {item.notes && <div className="text-sm text-gray-500 mt-2">{item.notes}</div>}
              {examples.slice(0, SHOWN_EXAMPLES).map((ex, i) => (
                <div key={i} className="mt-3 text-sm text-left bg-gray-800 rounded-lg p-3">
                  <div className="flex items-start justify-between gap-1">
                    <Ruby text={ex.japanese} className="text-gray-200" />
                    <SpeakButton text={ex.japanese} className="shrink-0 -mt-1" size={14} />
                  </div>
                  <div className="text-gray-500 mt-1">{ex.english}</div>
                </div>
              ))}
              <button
                onClick={async (e) => {
                  e.stopPropagation()
                  setGeneratingExample(true)
                  try {
                    const ex = await api.generateExampleSentence(item.id)
                    setGeneratedExample(ex)
                  } catch (err) {
                    console.error(err)
                  }
                  setGeneratingExample(false)
                }}
                disabled={generatingExample}
                className="mt-3 flex items-center gap-1.5 text-xs text-indigo-400 border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
              >
                {generatingExample
                  ? <><Loader2 size={13} className="animate-spin" /> Generating…</>
                  : <><Sparkles size={13} /> {generatedExample ? 'New example' : 'Generate example'}</>
                }
              </button>
              {generatedExample && (
                <div className="mt-2 text-sm text-left bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-3">
                  <div className="flex items-start justify-between gap-1">
                    <Ruby text={generatedExample.japanese} className="text-gray-200" />
                    <SpeakButton text={generatedExample.japanese} className="shrink-0 -mt-1" size={14} />
                  </div>
                  <div className="text-gray-500 mt-1">{generatedExample.english}</div>
                </div>
              )}
            </div>
          )}
        </div>

        {revealed && ratingButtons}
      </div>
    )
  }

  // AI-generated question modes
  return (
    <div className="max-w-lg mx-auto space-y-4">
      <div className="flex justify-between items-center text-sm text-gray-500">
        <span>{progress}</span>
        <button onClick={() => setMode(null)} className="text-gray-500 hover:text-gray-300">Exit</button>
      </div>

      {question ? (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-4">
          <div className="text-sm text-gray-500 uppercase font-medium">
            {mode === 'sentence_build'
              ? 'Translate to Japanese'
              : mode === 'grammar_drill'
                ? 'Choose the correct usage'
                : mode === 'cloze'
                  ? 'Recall the missing word'
                  : 'Fill in the blank'}
          </div>

          {mode === 'sentence_build' ? (
            <>
              <div className="text-xl font-medium text-gray-100 leading-relaxed">
                {question.prompt}
              </div>
              {(question.vocabulary?.length > 0 || question.context) && (
                <div className="text-sm">
                  <button
                    onClick={() => setHintsRevealed(v => !v)}
                    className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 transition-colors"
                  >
                    {hintsRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                    {hintsRevealed ? 'Hide' : 'Show'} hints
                  </button>
                  {hintsRevealed && (
                    <div className="mt-2 space-y-2">
                      {question.vocabulary?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {question.vocabulary.map((v, i) => (
                            <span
                              key={i}
                              className="inline-flex items-baseline gap-1.5 bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1 text-sm"
                            >
                              <Ruby text={v.japanese} className="text-gray-100" />
                              {v.meaning && <span className="text-gray-500 text-xs">{v.meaning}</span>}
                            </span>
                          ))}
                        </div>
                      )}
                      {question.context && <div className="text-gray-500">{question.context}</div>}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <Ruby text={question.prompt} className="text-xl" />
              {question.context && <div className="text-sm text-gray-500">{question.context}</div>}
              {mode === 'cloze' && (
                <div className="text-xs text-gray-600">Kanji or kana both count.</div>
              )}
            </>
          )}

          {question.translation && mode !== 'sentence_build' && (
            <div className="text-sm">
              <button
                onClick={() => setTranslationRevealed(v => !v)}
                className="flex items-center gap-1.5 text-gray-600 hover:text-gray-400 transition-colors"
              >
                {translationRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                {translationRevealed ? 'Hide' : 'Show'} translation
              </button>
              {translationRevealed && (
                <div className="mt-1.5 text-gray-500">{question.translation}</div>
              )}
            </div>
          )}

          {question.options.length > 0 && !answerChecked && (
            <div className="grid grid-cols-2 gap-2">
              {question.options.map((opt, i) => (
                <button key={i} onClick={() => { setUserAnswer(opt); checkAnswer() }}
                  className="border border-gray-700 rounded-lg px-3 py-2 text-left hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-colors">
                  <Ruby text={opt} />
                </button>
              ))}
            </div>
          )}

          {question.options.length === 0 && !answerChecked && (
            <div>
              <input
                value={userAnswer}
                onChange={e => setUserAnswer(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && userAnswer && checkAnswer()}
                className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg px-3 py-2 jp-text focus:ring-2 focus:ring-indigo-500 outline-none"
                placeholder="Type your answer..."
                autoFocus
              />
              <button onClick={checkAnswer} disabled={!userAnswer}
                className="mt-2 w-full bg-indigo-600 text-white py-2 rounded-lg font-medium hover:bg-indigo-500 disabled:opacity-50">
                Check
              </button>
            </div>
          )}

          {answerChecked && mode === 'sentence_build' && (
            evaluating ? (
              <div className="border-t border-gray-700 pt-4 flex items-center gap-2 text-gray-500 text-sm">
                <Loader2 size={15} className="animate-spin" /> Evaluating your answer…
              </div>
            ) : evaluation && (() => {
              const { verdict, feedback, corrected } = evaluation
              const isCorrect = verdict === 'correct'
              const isPartial = verdict === 'partial'
              return (
                <div className={`border-t pt-4 space-y-2 ${isCorrect ? 'border-green-500/30' : isPartial ? 'border-yellow-500/30' : 'border-red-500/30'}`}>
                  {isCorrect ? (
                    <div className="flex items-center gap-2 text-green-400 font-medium">
                      <CheckCircle size={18} /> Correct!
                    </div>
                  ) : isPartial ? (
                    <div className="flex items-center gap-2 text-yellow-400 font-medium">
                      <AlertCircle size={18} /> Almost there
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-red-400 font-medium">
                      <X size={18} /> Incorrect
                    </div>
                  )}
                  <div className="text-sm">
                    <span className="text-gray-500">Your answer: </span>
                    <Ruby text={userAnswer} className="text-gray-200" />
                  </div>
                  {feedback && <div className="text-sm text-gray-400">{feedback}</div>}
                  {corrected && (
                    <div className="text-sm">
                      <span className="text-gray-500">Corrected: </span>
                      <Ruby text={corrected} className="text-gray-200" />
                    </div>
                  )}
                  <div className="text-sm text-gray-500">Reference answer:</div>
                  <Ruby text={question.answer} className="text-lg font-medium text-gray-100" />
                </div>
              )
            })()
          )}

          {answerChecked && mode !== 'sentence_build' && (() => {
            const isCorrect = isAnswerAccepted(userAnswer, question)
            // For cloze the sentence with the blank filled back in is the thing
            // worth reading aloud, not the bare word.
            const spoken = mode === 'cloze'
              ? question.prompt.replace(CLOZE_BLANK, question.answer)
              : question.answer
            return (
              <div className={`border-t pt-4 space-y-2 ${isCorrect ? 'border-green-500/30' : 'border-red-500/30'}`}>
                {isCorrect ? (
                  <div className="flex items-center gap-2 text-green-400 font-medium">
                    <CheckCircle size={18} /> Correct!
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 text-red-400 font-medium">
                      <X size={18} /> Incorrect
                    </div>
                    {userAnswer && (
                      <div className="text-sm text-red-300/70">
                        Your answer: <Ruby text={userAnswer} />
                      </div>
                    )}
                  </>
                )}
                <div className="text-sm text-gray-500">Correct answer:</div>
                <div className="flex items-center gap-1">
                  <Ruby text={question.answer} className="text-lg font-medium text-gray-100" />
                  <SpeakButton text={spoken} label="Read the sentence aloud" />
                </div>
                {mode === 'cloze' && question.translation && (
                  <div className="text-sm text-gray-500">{question.translation}</div>
                )}
              </div>
            )
          })()}
        </div>
      ) : error ? (
        <div className="bg-gray-900 rounded-2xl border border-red-500/30 p-6 space-y-3 text-center">
          <X className="mx-auto text-red-400" size={28} />
          <div className="text-sm text-red-300/90">{error}</div>
          <div className="flex gap-2 justify-center pt-1">
            <button onClick={retryQuestion}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-500 text-sm">
              Try again
            </button>
            <button onClick={exitStudy}
              className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-800 text-sm">
              Exit
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-4">
          <SkeletonLine width="40%" className="h-3" />
          <SkeletonLine width="85%" className="h-5" />
          <div className="grid grid-cols-2 gap-2 pt-2">
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
            <Skeleton className="h-10 rounded-lg" />
          </div>
        </div>
      )}

      {answerChecked && (mode !== 'sentence_build' || evaluation) && continueControl}
    </div>
  )
}
