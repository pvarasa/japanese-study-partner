import { CheckCircle, X } from 'lucide-react'
import LevelBadge from '../components/LevelBadge'
import { Skeleton, SkeletonLine } from '../components/Skeleton'
import FlashcardCard from './study/FlashcardCard'
import QuestionCard from './study/QuestionCard'
import { MODES, START_ERROR } from './study/studyLogic'
import { useStudySession } from './study/useStudySession'

export default function Study() {
  const s = useStudySession()

  // Mode selection
  if (!s.mode) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Study</h1>
          <LevelBadge />
        </div>
        <div className="space-y-1.5">
          <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
            <button
              onClick={() => s.setPractice(false)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                !s.practice ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Due Reviews
            </button>
            <button
              onClick={() => s.setPractice(true)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                s.practice ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Practice
            </button>
          </div>
          {s.practice && (
            <p className="text-xs text-gray-500">
              Extra reps from your whole library. Doesn't affect scheduling or leech tracking.
            </p>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {MODES.map(m => (
            <button
              key={m.id}
              onClick={() => s.startStudy(m.id)}
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

  if (s.loading) {
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
  if (s.done) {
    const accuracy = s.sessionStats.reviewed > 0
      ? Math.round(s.sessionStats.correct / s.sessionStats.reviewed * 100)
      : 0
    return (
      <div className="text-center py-12 space-y-4">
        <CheckCircle className="mx-auto text-green-400" size={48} />
        <h2 className="text-2xl font-bold">
          {s.items.length === 0
            ? (s.practice ? 'Nothing to practice yet' : 'All caught up!')
            : 'Session Complete!'}
        </h2>
        {s.sessionStats.reviewed > 0 && (
          <div className="text-gray-400">
            <p>Reviewed: {s.sessionStats.reviewed} items</p>
            <p>Accuracy: {accuracy}%</p>
          </div>
        )}
        <div className="flex gap-3 justify-center">
          <button onClick={s.exitStudy}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-500">
            Back to modes
          </button>
          <button onClick={() => s.startStudy(s.mode)}
            className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-800">
            Study again
          </button>
        </div>
      </div>
    )
  }

  const item = s.items[s.current]

  // Starting failed before any cards arrived.
  if (!item) {
    return (
      <div className="max-w-lg mx-auto bg-gray-900 rounded-2xl border border-red-500/30 p-6 space-y-3 text-center">
        <X className="mx-auto text-red-400" size={28} />
        <div className="text-sm text-red-300/90">{s.error || START_ERROR}</div>
        <div className="flex gap-2 justify-center pt-1">
          <button onClick={() => s.startStudy(s.mode)}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-500 text-sm">
            Try again
          </button>
          <button onClick={s.exitStudy}
            className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg hover:bg-gray-800 text-sm">
            Back to modes
          </button>
        </div>
      </div>
    )
  }

  const progress = `${s.current + 1} / ${s.items.length}`

  if (s.mode === 'flashcard_jp' || s.mode === 'flashcard_en') {
    return (
      <FlashcardCard
        mode={s.mode}
        item={item}
        progress={progress}
        revealed={s.revealed}
        setRevealed={s.setRevealed}
        shownExamples={s.shownExamples}
        generatedExample={s.generatedExample}
        generatingExample={s.generatingExample}
        generateExample={s.generateExample}
        error={s.error}
        submitting={s.submitting}
        onRate={s.handleRate}
        exitStudy={s.exitStudy}
      />
    )
  }

  return (
    <QuestionCard
      mode={s.mode}
      question={s.question}
      userAnswer={s.userAnswer}
      setUserAnswer={s.setUserAnswer}
      answerChecked={s.answerChecked}
      checkAnswer={s.checkAnswer}
      evaluating={s.evaluating}
      evaluation={s.evaluation}
      hintsRevealed={s.hintsRevealed}
      setHintsRevealed={s.setHintsRevealed}
      translationRevealed={s.translationRevealed}
      setTranslationRevealed={s.setTranslationRevealed}
      error={s.error}
      retry={s.retry}
      exitStudy={s.exitStudy}
      submitting={s.submitting}
      onRate={s.handleRate}
      practice={s.practice}
      progress={progress}
    />
  )
}
