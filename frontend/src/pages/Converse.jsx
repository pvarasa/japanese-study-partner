import { useCallback, useEffect, useRef, useState } from 'react'
import { Mic, Square, Loader2, Send, RefreshCw, CheckCircle, MessagesSquare, ArrowRight } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
import LevelBadge from '../components/LevelBadge'
import { useFeatures } from '../context/FeaturesContext'
import { loadValue, saveValue } from '../storage'

const MAX_RECORD_MS = 30_000

// The conversation is persisted as one snapshot, so leaving the page (or the
// browser reloading the tab after an app switch) resumes it mid-thread.
const CONVERSATION_KEY = 'converse-session'
const CONVERSATION_MAX_AGE_MS = 6 * 60 * 60 * 1000

export default function Converse() {
  const { whisperEnabled } = useFeatures()
  const [restored] = useState(() => loadValue(CONVERSATION_KEY, null, { maxAgeMs: CONVERSATION_MAX_AGE_MS }))
  const [starting, setStarting] = useState(false)
  const [topic, setTopic] = useState(restored?.topic ?? null)
  const [question, setQuestion] = useState(restored?.question ?? null)
  const [questionHint, setQuestionHint] = useState(restored?.questionHint ?? '')
  const [history, setHistory] = useState(restored?.history ?? [])  // {role, content}
  const [userText, setUserText] = useState(restored?.userText ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState(restored?.feedback ?? null)  // ReplyOut
  const [error, setError] = useState(null)

  // Recording state
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [micError, setMicError] = useState(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const recordTimeoutRef = useRef(null)
  // Set on unmount so a recording stopped by the cleanup isn't sent off for
  // transcription into a page that no longer exists.
  const unmountedRef = useRef(false)

  // Turn counts aren't tracked here — each turn posts its own increment to
  // the server as it happens. Conversation still reports corrections-free
  // turns as "correct", but the dashboard excludes converse from accuracy
  // entirely, since a conversation has no right answer.
  //
  // The session is deliberately *not* ended on unmount: the conversation
  // resumes when the learner comes back, and a fetch fired from an unmount
  // path is unreliable anyway. Starting a new topic closes it.
  const [sessionId, setSessionId] = useState(restored?.sessionId ?? null)

  useEffect(() => {
    saveValue(CONVERSATION_KEY, question
      ? { topic, question, questionHint, history, userText, feedback, sessionId }
      : null)
  }, [topic, question, questionHint, history, userText, feedback, sessionId])

  const endSession = () => {
    if (sessionId == null) return
    setSessionId(null)
    // Counts are omitted deliberately: each turn already recorded itself.
    api.endSession(sessionId).catch(() => { /* the turns themselves are already recorded */ })
  }

  const startConversation = async () => {
    setStarting(true)
    setError(null)
    try {
      const sess = await api.startSession('converse')
      endSession()
      setSessionId(sess.session_id)

      const s = await api.converseStart()
      setTopic(s.topic)
      setQuestion(s.question)
      setQuestionHint(s.english_hint)
      // Cleared only once the new topic has arrived, so a failed start
      // leaves the current conversation on screen.
      setFeedback(null)
      setHistory([])
      setUserText('')
    } catch (err) {
      setError(err.message || 'Failed to start')
    }
    setStarting(false)
  }

  const submitAnswer = async () => {
    if (!userText.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const turnHistory = [
        ...history,
        { role: 'tutor', content: question },
      ]
      const res = await api.converseReply(turnHistory, userText)
      setFeedback(res)
      setHistory([
        ...turnHistory,
        { role: 'learner', content: userText },
      ])
      const clean = res.corrections?.length === 0
      // Record the turn as it happens. This used to be reported only from the
      // unmount cleanup, and an async fetch fired during unmount or tab-close
      // routinely never lands — every conversation ever held recorded zero.
      if (sessionId != null) {
        api.sessionProgress(sessionId, {
          reviewed: 1,
          correct: clean ? 1 : 0,
        }).catch(() => { /* the conversation matters more than the counter */ })
      }
    } catch (err) {
      setError(err.message || 'Failed to submit')
    }
    setSubmitting(false)
  }

  const continueConversation = () => {
    if (!feedback) return
    // The follow-up becomes the current question; submitAnswer adds it to the
    // history when it's answered. Appending it here too sent every question
    // after the first to the tutor twice.
    setQuestion(feedback.follow_up)
    setQuestionHint(feedback.follow_up_hint)
    setFeedback(null)
    setUserText('')
  }

  // Only touches refs and a state setter, so it's stable across renders and
  // safe to hand to the listeners and effects below.
  const stopRecording = useCallback(() => {
    if (recordTimeoutRef.current) {
      clearTimeout(recordTimeoutRef.current)
      recordTimeoutRef.current = null
    }
    const mr = mediaRecorderRef.current
    if (mr && mr.state !== 'inactive') mr.stop()
    setRecording(false)
  }, [])

  const startRecording = async () => {
    setMicError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
        if (blob.size === 0 || unmountedRef.current) return
        setTranscribing(true)
        try {
          const { text } = await api.transcribe(blob, 'audio.webm')
          if (text) {
            setUserText((prev) => (prev ? prev + ' ' + text : text))
          }
        } catch (err) {
          setMicError(err.message || 'Transcription failed')
        }
        setTranscribing(false)
      }
      // The OS can pull the mic out from under us (a phone call, another app
      // claiming it); stop cleanly so the UI doesn't sit in "Recording…".
      stream.getAudioTracks().forEach((t) => t.addEventListener('ended', stopRecording))
      mr.start()
      mediaRecorderRef.current = mr
      setRecording(true)
      recordTimeoutRef.current = setTimeout(stopRecording, MAX_RECORD_MS)
    } catch (err) {
      setMicError(err.message || 'Microphone unavailable')
    }
  }

  // Switching away mid-recording: stop and transcribe what was captured.
  // Mobile browsers suspend a hidden page's mic anyway, so carrying on would
  // only produce a truncated clip with the UI still claiming to record.
  useEffect(() => {
    if (!recording) return
    const onVisibilityChange = () => { if (document.hidden) stopRecording() }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [recording, stopRecording])

  // Leaving the page mid-recording must release the microphone; otherwise
  // the stream (and the browser's recording indicator) stays live.
  useEffect(() => {
    unmountedRef.current = false
    return () => {
      unmountedRef.current = true
      stopRecording()
    }
  }, [stopRecording])

  if (!question) {
    return (
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Conversation</h1>
          <LevelBadge />
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center">
          <MessagesSquare className="mx-auto mb-3 text-indigo-400" size={36} />
          <p className="text-gray-400 mb-5">
            The tutor asks an open-ended question. You reply in Japanese — typed or spoken — and get corrections and a natural rewrite.
          </p>
          <button
            onClick={startConversation}
            disabled={starting}
            className="bg-indigo-500 hover:bg-indigo-400 disabled:opacity-50 text-white font-medium px-5 py-2.5 rounded-lg inline-flex items-center gap-2"
          >
            {starting ? <Loader2 className="animate-spin" size={16} /> : <MessagesSquare size={16} />}
            {starting ? 'Starting…' : 'Start conversation'}
          </button>
          {error && <p className="mt-4 text-red-400 text-sm">{error}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Topic header */}
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-gray-400 truncate">
          Topic: <span className="text-gray-200">{topic}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <LevelBadge />
          <button
            onClick={startConversation}
            disabled={starting || submitting}
            className="text-xs text-gray-400 hover:text-gray-200 disabled:opacity-50 inline-flex items-center gap-1"
          >
            <RefreshCw size={12} className={starting ? 'animate-spin' : ''} /> New topic
          </button>
        </div>
      </div>

      {/* Question card */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 sm:p-8">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-3">Tutor</div>
        <Ruby text={question} className="jp-reading text-xl" />
        {questionHint && <div className="text-sm text-gray-500 mt-3">{questionHint}</div>}
      </div>

      {/* Answer area */}
      {!feedback && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
          <textarea
            value={userText}
            onChange={(e) => setUserText(e.target.value)}
            placeholder={whisperEnabled ? '日本語で答えてください… (type or use the mic)' : '日本語で答えてください…'}
            rows={5}
            className="jp-text w-full bg-gray-800 border border-gray-800 rounded-lg px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500"
            disabled={submitting}
          />

          <div className="flex items-center gap-2 flex-wrap">
            {whisperEnabled && (
              !recording ? (
                <button
                  onClick={startRecording}
                  disabled={transcribing || submitting}
                  className="inline-flex items-center gap-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-200 px-3 py-2 rounded-lg text-sm"
                >
                  {transcribing ? <Loader2 className="animate-spin" size={16} /> : <Mic size={16} />}
                  {transcribing ? 'Transcribing…' : 'Record'}
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="inline-flex items-center gap-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 px-3 py-2 rounded-lg text-sm"
                >
                  <Square size={16} /> Stop
                </button>
              )
            )}

            <button
              onClick={submitAnswer}
              disabled={submitting || !userText.trim()}
              className="inline-flex items-center gap-2 bg-indigo-500 hover:bg-indigo-400 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm ml-auto"
            >
              {submitting ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
              {submitting ? 'Checking…' : 'Submit'}
            </button>
          </div>

          {whisperEnabled && micError && <div className="text-sm text-red-400">{micError}</div>}
          {error && <div className="text-sm text-red-400">{error}</div>}
          {recording && <div className="text-xs text-gray-500">Recording… (max 30s)</div>}
        </div>
      )}

      {/* Feedback */}
      {feedback && (
        <div className="space-y-3">
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            {/* Your answer — muted header */}
            <div className="px-5 py-3 bg-gray-800/40 border-b border-gray-800">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Your answer</div>
              <div className="jp-text text-sm text-gray-400 whitespace-pre-wrap">{userText}</div>
            </div>

            {/* Corrections — inline diffs */}
            {feedback.corrections.length > 0 ? (
              <div className="px-5 py-4 border-b border-gray-800">
                <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                  {feedback.corrections.length} correction{feedback.corrections.length > 1 ? 's' : ''}
                </div>
                <ul className="space-y-2.5">
                  {feedback.corrections.map((c, i) => (
                    <li key={i} className="text-sm">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="jp-text text-red-400/80 line-through decoration-red-400/50">{c.original}</span>
                        <ArrowRight size={12} className="text-gray-600 shrink-0" />
                        <span className="jp-text text-green-400"><Ruby text={c.fixed} /></span>
                      </div>
                      {c.note && <div className="text-xs text-gray-500 mt-0.5">{c.note}</div>}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="px-5 py-3 border-b border-gray-800 flex items-center gap-2 text-green-400 text-sm">
                <CheckCircle size={14} /> Nothing to correct — nice!
              </div>
            )}

            {/* Natural rewrite — focal element */}
            <div className="px-5 py-5">
              <div className="text-xs uppercase tracking-wide text-indigo-400 mb-2">Natural rewrite</div>
              <Ruby text={feedback.rewrite} className="jp-reading text-lg" />
              {feedback.feedback && <div className="text-sm text-gray-400 mt-3">{feedback.feedback}</div>}
            </div>
          </div>

          {error && <div className="text-sm text-red-400">{error}</div>}
          <button
            onClick={continueConversation}
            className="w-full bg-indigo-500 hover:bg-indigo-400 text-white font-medium px-4 py-3 rounded-lg"
          >
            Continue →
          </button>
        </div>
      )}
    </div>
  )
}
