import { useState } from 'react'
import { RotateCcw, ArrowRight, Zap, CheckCircle, X, Sparkles, Loader2 } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
import LevelBadge from '../components/LevelBadge'
import { Skeleton, SkeletonLine } from '../components/Skeleton'

const MODES = [
  { id: 'flashcard_jp', label: 'JP → EN', desc: 'See Japanese, recall English' },
  { id: 'flashcard_en', label: 'EN → JP', desc: 'See English, recall Japanese' },
  { id: 'fill_blank', label: 'Fill Blank', desc: 'Complete the sentence' },
  { id: 'sentence_build', label: 'Build Sentence', desc: 'Translate to Japanese' },
]

export default function Study() {
  const [mode, setMode] = useState(null)
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

  const startStudy = async (m) => {
    setMode(m)
    setLoading(true)
    try {
      const due = await api.getDueItems({ limit: 20 })
      if (due.length === 0) {
        setItems([])
        setDone(true)
        setLoading(false)
        return
      }
      setItems(due)
      setCurrent(0)
      setRevealed(false)
      setDone(false)
      setSessionStats({ reviewed: 0, correct: 0 })
      const sess = await api.startSession(m)
      setSessionId(sess.session_id)

      if (m === 'fill_blank' || m === 'sentence_build') {
        const q = await api.generateQuestion(due[0].id, m)
        setQuestion(q)
      }
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  const handleRate = async (rating) => {
    const item = items[current]
    await api.reviewItem(item.id, rating)
    const stats = {
      reviewed: sessionStats.reviewed + 1,
      correct: sessionStats.correct + (rating !== 'again' ? 1 : 0),
    }
    setSessionStats(stats)

    if (current + 1 >= items.length) {
      if (sessionId) await api.endSession(sessionId, stats.reviewed, stats.correct)
      setDone(true)
    } else {
      setCurrent(current + 1)
      setRevealed(false)
      setQuestion(null)
      setUserAnswer('')
      setAnswerChecked(false)
      setGeneratedExample(null)
      setGeneratingExample(false)

      if (mode === 'fill_blank' || mode === 'sentence_build') {
        setLoading(true)
        const q = await api.generateQuestion(items[current + 1].id, mode)
        setQuestion(q)
        setLoading(false)
      }
    }
  }

  const checkAnswer = () => {
    setAnswerChecked(true)
    setRevealed(true)
  }

  // Mode selection
  if (!mode) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Study</h1>
          <LevelBadge />
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
          {items.length === 0 ? 'All caught up!' : 'Session Complete!'}
        </h2>
        {sessionStats.reviewed > 0 && (
          <div className="text-gray-400">
            <p>Reviewed: {sessionStats.reviewed} items</p>
            <p>Accuracy: {accuracy}%</p>
          </div>
        )}
        <div className="flex gap-3 justify-center">
          <button onClick={() => { setMode(null); setDone(false) }}
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
  const examples = item.example_sentences ? JSON.parse(item.example_sentences) : []

  const ratingButtons = (
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
  )

  // Flashcard modes
  if (mode === 'flashcard_jp' || mode === 'flashcard_en') {
    const isJpToEn = mode === 'flashcard_jp'
    return (
      <div className="max-w-lg mx-auto space-y-4">
        <div className="flex justify-between items-center text-sm text-gray-500">
          <span>{progress}</span>
          <button onClick={() => setMode(null)} className="text-gray-500 hover:text-gray-300">Exit</button>
        </div>

        {/* Card */}
        <div
          className="bg-gray-900 rounded-2xl border border-gray-800 p-8 text-center min-h-[250px] flex flex-col justify-center cursor-pointer"
          onClick={() => setRevealed(true)}
        >
          {isJpToEn ? (
            <Ruby text={item.japanese} className="text-3xl font-medium mb-2" />
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
                <Ruby text={item.japanese} className="text-2xl font-medium" />
              )}
              {item.notes && <div className="text-sm text-gray-500 mt-2">{item.notes}</div>}
              {examples.length > 0 && (
                <div className="mt-3 text-sm text-left bg-gray-800 rounded-lg p-3">
                  <Ruby text={examples[0].japanese} className="text-gray-200" />
                  <div className="text-gray-500 mt-1">{examples[0].english}</div>
                </div>
              )}
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
                  <Ruby text={generatedExample.japanese} className="text-gray-200" />
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
            {mode === 'fill_blank' ? 'Fill in the blank' : 'Build the sentence'}
          </div>
          <Ruby text={question.prompt} className="text-xl" />
          {question.context && <div className="text-sm text-gray-500">{question.context}</div>}

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

          {answerChecked && (() => {
            const isCorrect = userAnswer.trim() === question.answer.trim()
              || question.options.length > 0 && userAnswer === question.answer
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
                <Ruby text={question.answer} className="text-lg font-medium text-gray-100" />
              </div>
            )
          })()}
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

      {answerChecked && ratingButtons}
    </div>
  )
}
