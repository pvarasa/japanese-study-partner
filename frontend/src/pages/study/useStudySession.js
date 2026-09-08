import { useMemo, useState } from 'react'
import { api } from '../../api'
import { GENERATED_MODES, QUESTION_ERROR, RATE_ERROR, SHOWN_EXAMPLES, parseExamples, pickExamples } from './studyLogic'

/**
 * Owns every piece of state and every handler the Study page needs — fetching
 * due/practice items, driving the flashcard vs. AI-question flow, submitting
 * reviews, and session lifecycle. Study.jsx stays pure rendering: it reads
 * this hook's return value and picks which screen to show.
 */
export function useStudySession() {
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

  // Reshuffled only when the card actually changes (`items` per session,
  // `current` per card) — not on every re-render — so the picked examples
  // stay put while the learner reveals/toggles hints on the same card.
  const shownExamples = useMemo(
    () => pickExamples(parseExamples(items[current]?.example_sentences), SHOWN_EXAMPLES),
    [items, current]
  )

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

  const generateExample = async () => {
    const item = items[current]
    if (!item) return
    setGeneratingExample(true)
    try {
      const ex = await api.generateExampleSentence(item.id)
      setGeneratedExample(ex)
    } catch (err) {
      console.error(err)
    }
    setGeneratingExample(false)
  }

  return {
    mode, practice, setPractice, items, current, revealed, setRevealed,
    sessionStats, question, userAnswer, setUserAnswer, answerChecked,
    loading, done, generatedExample, generatingExample, translationRevealed,
    setTranslationRevealed, hintsRevealed, setHintsRevealed, evaluating,
    evaluation, error, shownExamples,
    startStudy, retryQuestion, exitStudy, handleRate, checkAnswer, generateExample,
  }
}
