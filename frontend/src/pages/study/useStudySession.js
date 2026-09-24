import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import { usePersistentState } from '../../hooks/usePersistentState'
import { loadValue, saveValue } from '../../storage'
import {
  EVALUATE_ERROR, GENERATED_MODES, MODES, QUESTION_ERROR, RATE_ERROR, READING_MODE, SHOWN_EXAMPLES,
  START_ERROR, parseExamples, pickExamples,
} from './studyLogic'

const SESSION_KEY = 'study-session'
// A snapshot nobody has touched for this long is dropped instead of resumed:
// its due queue is stale, and the learner has likely studied elsewhere since.
const SESSION_MAX_AGE_MS = 6 * 60 * 60 * 1000

// Per-card state, cleared whenever the card changes.
const FRESH_CARD = {
  revealed: false,
  question: null,
  userAnswer: '',
  answerChecked: false,
  generatedExample: null,
  translationRevealed: false,
  hintsRevealed: false,
  evaluation: null,
}

const NO_SESSION = {
  mode: null,
  items: [],
  current: 0,
  sessionId: null,
  sessionStats: { reviewed: 0, correct: 0 },
  done: false,
  ...FRESH_CARD,
}

/** The persisted session, or NO_SESSION if there's nothing worth resuming. */
function restoreSession() {
  const saved = loadValue(SESSION_KEY, null, { maxAgeMs: SESSION_MAX_AGE_MS })
  if (!saved || !MODES.some(m => m.id === saved.mode) || !Array.isArray(saved.items)) {
    return NO_SESSION
  }
  // A snapshot taken while the session was still starting has no card to show.
  const onCard = Number.isInteger(saved.current) && saved.current >= 0 && saved.current < saved.items.length
  if (!saved.done && !onCard) return NO_SESSION
  return { ...NO_SESSION, ...saved }
}

/** Close a session without counts — progress is already recorded per review. */
function endSession(id) {
  if (id == null) return
  api.endSession(id).catch(() => { /* ignore — the reviews themselves are already recorded */ })
}

/**
 * Fetch the question for the first item at or after `from` that has one.
 *
 * Cloze can legitimately produce nothing for an item (no stored example
 * actually uses the word), which the server reports as a 422. Skip those
 * instead of stalling the session on an error the learner can't act on.
 */
async function loadQuestionFrom(list, from, mode) {
  for (let i = from; i < list.length; i++) {
    try {
      return { index: i, question: await api.generateQuestion(list[i].id, mode) }
    } catch (err) {
      if (err.status === 422) continue
      throw err
    }
  }
  return null
}

/**
 * Owns every piece of state and every handler the Study page needs — fetching
 * due/practice items, driving the flashcard vs. AI-question flow, submitting
 * reviews, and session lifecycle. Study.jsx stays pure rendering: it reads
 * this hook's return value and picks which screen to show.
 *
 * The session lives in one object persisted to localStorage, so leaving the
 * page — navigating elsewhere in the app, or the browser reloading the tab
 * after the learner switched apps — puts them back on the same card instead
 * of dropping the session.
 */
export function useStudySession() {
  // Practice pulls extra reps from the whole library instead of just due
  // items, and reviewing them doesn't touch SRS scheduling. Toggled on the
  // mode-selection screen, then fixed for the life of the session.
  const [practice, setPractice] = usePersistentState('study-practice', false)
  const [session, setSession] = useState(restoreSession)
  // Transient: a request in flight doesn't survive a reload, so none of these
  // are persisted. Work that was pending when the page went away is picked
  // back up by the effects below, which key off the persisted state alone.
  const [startingSession, setStartingSession] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [generatingFor, setGeneratingFor] = useState(null)
  const [error, setError] = useState(null)

  const {
    mode, items, current, done, question, userAnswer, answerChecked, evaluation,
  } = session

  // Latest session for async continuations, which must not act on a session
  // the learner has since left. Synced after commit, never during render.
  const sessionRef = useRef(session)
  // Bumped by every start and exit, so a superseded start can tell.
  const startRunRef = useRef(0)
  // A ref, not the `submitting` state, so a double tap landing before the
  // re-render still sees the first submission.
  const submittingRef = useRef(false)

  useEffect(() => {
    sessionRef.current = session
    saveValue(SESSION_KEY, session.mode ? session : null)
  }, [session])

  // Reshuffled only when the card actually changes (`items` per session,
  // `current` per card) — not on every re-render — so the picked examples
  // stay put while the learner reveals/toggles hints on the same card.
  const shownExamples = useMemo(
    () => pickExamples(parseExamples(items[current]?.example_sentences), SHOWN_EXAMPLES),
    [items, current]
  )

  // Fetched declaratively, so starting, advancing, retrying after an error
  // and resuming after a reload all load the current card's question the
  // same way — and a result for a card that's no longer current is dropped.
  const needsQuestion = GENERATED_MODES.includes(mode) && !done && items.length > 0 && !question && !error

  useEffect(() => {
    if (!needsQuestion) return
    let cancelled = false
    loadQuestionFrom(items, current, mode)
      .then((found) => {
        if (cancelled) return
        if (found) {
          setSession(prev => ({ ...prev, current: found.index, question: found.question }))
        } else {
          // Every remaining item was skipped — nothing left to ask.
          endSession(sessionRef.current.sessionId)
          setSession(prev => ({ ...prev, done: true, sessionId: null }))
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || QUESTION_ERROR)
      })
    return () => { cancelled = true }
  }, [needsQuestion, items, current, mode])

  const needsEvaluation = mode === 'sentence_build' && answerChecked && !evaluation && !error

  useEffect(() => {
    if (!needsEvaluation) return
    let cancelled = false
    api.evaluateAnswer(userAnswer, question.answer, question.prompt)
      .then((result) => {
        if (!cancelled) setSession(prev => ({ ...prev, evaluation: result }))
      })
      .catch((err) => {
        // Surface it with a retry rather than inventing an "incorrect"
        // verdict: that would schedule the card as a lapse, and a dropped
        // connection is not a wrong answer.
        if (!cancelled) setError(err.message || EVALUATE_ERROR)
      })
    return () => { cancelled = true }
  }, [needsEvaluation, userAnswer, question])

  const startStudy = async (m) => {
    const run = ++startRunRef.current
    endSession(sessionRef.current.sessionId)
    setSession({ ...NO_SESSION, mode: m })
    setError(null)
    setStartingSession(true)
    try {
      const fetchItems = m === READING_MODE
        ? (practice ? api.getReadingPractice : api.getReadingDue)
        : (practice ? api.getPracticeItems : api.getDueItems)
      const due = await fetchItems({ limit: 20 })
      if (startRunRef.current !== run) return
      if (due.length === 0) {
        setSession(prev => ({ ...prev, done: true }))
        return
      }
      // Distinct mode label keeps practice reps out of accuracy_today and the
      // retention chart (see GRADED_MODES in routers/study.py) while still
      // counting toward studied-today and the streak, same as converse turns.
      const sess = await api.startSession(practice ? `practice_${m}` : m)
      if (startRunRef.current !== run) {
        endSession(sess.session_id)
        return
      }
      setSession(prev => ({ ...prev, items: due, current: 0, sessionId: sess.session_id }))
    } catch (err) {
      if (startRunRef.current === run) setError(err.message || START_ERROR)
    } finally {
      if (startRunRef.current === run) setStartingSession(false)
    }
  }

  // Clearing the error re-arms whichever fetch it stopped (question or evaluation).
  const retry = () => setError(null)

  const exitStudy = () => {
    startRunRef.current++
    endSession(session.sessionId)
    setSession(NO_SESSION)
    setError(null)
    setStartingSession(false)
  }

  const handleRate = async (rating) => {
    const item = items[current]
    if (!item || submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    setError(null)
    try {
      // Passing the session id records this review against the session
      // server-side, so quitting part-way keeps what was already done.
      await api.reviewItem(
        item.id, rating, session.sessionId, practice, mode === READING_MODE ? 'reading' : 'meaning',
      )
    } catch (err) {
      // Keep the card in place so the user can retry the same rating.
      setError(err.message || RATE_ERROR)
      return
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }

    // The learner may have exited (or restarted) while the review was saving.
    const now = sessionRef.current
    if (now.items !== items || now.current !== current) return

    const last = current + 1 >= items.length
    if (last) endSession(session.sessionId)
    setSession((prev) => {
      if (prev.items !== items || prev.current !== current) return prev
      const sessionStats = {
        reviewed: prev.sessionStats.reviewed + 1,
        // Strict: only a clean recall counts. "Hard" means it was dredged up.
        correct: prev.sessionStats.correct + (rating === 'good' ? 1 : 0),
      }
      return last
        ? { ...prev, sessionStats, done: true, sessionId: null }
        : { ...prev, ...FRESH_CARD, sessionStats, current: current + 1 }
    })
  }

  // For sentence_build this also kicks off the evaluation effect above.
  const checkAnswer = () => {
    setSession(prev => ({ ...prev, answerChecked: true, revealed: true }))
  }

  const generateExample = async () => {
    const item = items[current]
    if (!item || generatingFor === item.id) return
    setGeneratingFor(item.id)
    try {
      const ex = await api.generateExampleSentence(item.id)
      // Only attach it to the card it was generated for.
      setSession(prev => (prev.items === items && prev.current === current
        ? { ...prev, generatedExample: ex }
        : prev))
    } catch (err) {
      console.error(err)
    }
    setGeneratingFor(id => (id === item.id ? null : id))
  }

  // Setter for one session field, accepting a value or an updater like useState's.
  const setField = (field) => (value) => setSession(prev => ({
    ...prev,
    [field]: typeof value === 'function' ? value(prev[field]) : value,
  }))

  return {
    mode, practice, setPractice, items, current,
    revealed: session.revealed, setRevealed: setField('revealed'),
    sessionStats: session.sessionStats,
    question, userAnswer, setUserAnswer: setField('userAnswer'), answerChecked,
    loading: startingSession || needsQuestion,
    done,
    generatedExample: session.generatedExample,
    generatingExample: generatingFor != null && generatingFor === items[current]?.id,
    translationRevealed: session.translationRevealed, setTranslationRevealed: setField('translationRevealed'),
    hintsRevealed: session.hintsRevealed, setHintsRevealed: setField('hintsRevealed'),
    evaluating: needsEvaluation, evaluation, error, submitting, shownExamples,
    startStudy, retry, exitStudy, handleRate, checkAnswer, generateExample,
  }
}
