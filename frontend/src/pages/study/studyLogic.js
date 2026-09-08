// Pure helpers and constants for the Study page — no JSX, no hooks, so they're
// easy to reason about (and reuse) independently of how the page renders.

export const MODES = [
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
export const GENERATED_MODES = ['cloze', 'fill_blank', 'sentence_build', 'grammar_drill']

// Fallback when the generate request fails without a server-provided detail.
export const QUESTION_ERROR = 'Failed to load this question. Please try again.'
// Fallback when submitting a review rating fails.
export const RATE_ERROR = 'Failed to save your review. Please try again.'

// The placeholder the server blanks the target word out with. Must match
// BLANK in backend/app/cloze.py — it's what turns a cloze prompt back into a
// full sentence for the read-aloud button.
export const CLOZE_BLANK = '＿＿＿'

// How many stored examples the reveal shows. Items are generated with
// EXAMPLES_PER_ITEM (app/enrich.py) of them, but older ingested rows can carry
// three or four — cap the card rather than letting its height vary per item.
export const SHOWN_EXAMPLES = 2

export const RATING_LABEL = { good: 'Good', hard: 'Hard', again: 'Again' }
export const RATING_COLOR = { good: 'text-green-400', hard: 'text-orange-400', again: 'text-red-400' }

/** Compare a typed answer against the accepted spellings. */
export function isAnswerAccepted(userAnswer, question) {
  const given = (userAnswer || '').trim()
  if (!given) return false
  const accepted = question.accepted?.length ? question.accepted : [question.answer]
  return accepted.some(a => a.trim() === given)
}

// `example_sentences` is a JSON string in a text column, authored by the LLM at
// ingest time and never validated as parseable. A malformed value used to throw
// during render and blank the page, so degrade to "no examples" instead.
export function parseExamples(raw) {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(e => e && typeof e.japanese === 'string')
  } catch {
    return []
  }
}

/**
 * Random sample of `n` examples, without replacement. A card whose stored
 * pool is larger than `n` (older ingests, or backfill top-ups) would
 * otherwise always reveal the same leading slice — memorizing "the sentence
 * that goes with this word" instead of recalling the word itself.
 */
export function pickExamples(examples, n) {
  const pool = [...examples]
  const picked = []
  while (pool.length && picked.length < n) {
    picked.push(pool.splice(Math.floor(Math.random() * pool.length), 1)[0])
  }
  return picked
}
