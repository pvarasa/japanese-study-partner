import { useEffect, useState } from 'react'
import { Volume2 } from 'lucide-react'

/**
 * Read Japanese text aloud via the browser's built-in speech synthesis.
 *
 * Deliberately not a server round-trip: every target platform (Windows, macOS,
 * iOS, Android) ships a ja-JP voice, so this needs no API key, no network, and
 * no audio files. The trade-off is that voice quality varies by OS, and a
 * machine with no Japanese voice installed gets no button at all rather than
 * an English voice mangling the kana.
 */

let voicePromise = null

function loadJapaneseVoice() {
  // Voices populate asynchronously in Chrome — getVoices() returns [] on the
  // first call and fires voiceschanged once they're ready. Resolved once and
  // shared, so every button doesn't re-subscribe.
  if (voicePromise) return voicePromise

  voicePromise = new Promise((resolve) => {
    const synth = window.speechSynthesis
    if (!synth) return resolve(null)

    const pick = () => {
      const voices = synth.getVoices()
      if (!voices.length) return null
      return voices.find(v => v.lang === 'ja-JP')
        || voices.find(v => v.lang?.toLowerCase().startsWith('ja'))
        || null
    }

    const immediate = pick()
    if (immediate) return resolve(immediate)

    let settled = false
    const done = (v) => { if (!settled) { settled = true; resolve(v) } }
    synth.addEventListener('voiceschanged', () => done(pick()), { once: true })
    // Some browsers never fire the event when there's nothing to load.
    setTimeout(() => done(pick()), 1500)
  })
  return voicePromise
}

export default function SpeakButton({ text, className = '', size = 15, label = 'Read aloud' }) {
  const [voice, setVoice] = useState(null)
  const [speaking, setSpeaking] = useState(false)

  useEffect(() => {
    let alive = true
    loadJapaneseVoice().then(v => { if (alive) setVoice(v) })
    return () => { alive = false }
  }, [])

  // No Japanese voice on this machine — render nothing rather than a button
  // that would read 環境 as "kan-kyoh".
  if (!voice || !text) return null

  const speak = (e) => {
    e.stopPropagation()   // cards flip on click; the speaker shouldn't flip them
    const synth = window.speechSynthesis
    synth.cancel()        // interrupt whatever is mid-sentence
    const utterance = new SpeechSynthesisUtterance(text)
    // lang is what actually matters — with it set, the browser picks a
    // Japanese voice on its own. Naming the exact voice is a refinement, so
    // don't let it failing take the whole utterance down with it.
    utterance.lang = voice.lang || 'ja-JP'
    try {
      utterance.voice = voice
    } catch { /* fall back to whatever the browser picks for utterance.lang */ }
    utterance.rate = 0.85 // native pace is fast for a learner
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => setSpeaking(false)
    setSpeaking(true)
    try {
      synth.speak(utterance)
    } catch {
      setSpeaking(false)
    }
  }

  return (
    <button
      onClick={speak}
      aria-label={label}
      title={label}
      className={`inline-flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:text-indigo-400 hover:bg-indigo-500/10 transition-colors ${speaking ? 'text-indigo-400' : ''} ${className}`}
    >
      <Volume2 size={size} className={speaking ? 'animate-pulse' : ''} />
    </button>
  )
}
