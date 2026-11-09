import { ScrollText, Star } from 'lucide-react'
import { SkeletonLine } from '../../components/Skeleton'

/**
 * One kanji in full: meaning, level, on/kun readings (with the one `word`
 * uses highlighted, when the detail says), the parts it's built from, where the
 * character comes from, common words that show its meaning at work, and the
 * library words that share it. Shared by the reading drill's reveal and the
 * Kanji page; `word` is '' on the latter, where no word is being drilled.
 *
 * Pass `onToggleMark` to show the mark star.
 */
export default function KanjiPanel({ word = '', family, detail, loading = false, marked = false, markPending = false, onToggleMark }) {
  return (
    <div className="flex gap-3 bg-gray-800/70 border border-gray-800 rounded-lg p-3">
      <div className="w-12 shrink-0 text-center">
        <div className="text-4xl leading-none text-gray-100"><span className="jp-text">{family.kanji}</span></div>
        {detail?.strokes && (
          <div className="mt-1.5 text-gray-500 leading-tight">
            <div className="text-xs text-gray-400">{detail.strokes}</div>
            <div className="text-[10px]">strokes</div>
          </div>
        )}
        {onToggleMark && (
          <button
            type="button"
            onClick={onToggleMark}
            disabled={markPending}
            aria-pressed={marked}
            title={marked ? 'Marked: on your Kanji page and in the Marked kanji drill. Tap to unmark' : 'Mark this kanji to come back to it'}
            className={`mt-2 p-1.5 rounded-lg transition-colors disabled:opacity-50 ${
              marked ? 'text-amber-400 bg-amber-500/15 hover:bg-amber-500/25' : 'text-gray-500 hover:text-amber-300 hover:bg-gray-700/60'
            }`}
          >
            <Star size={18} fill={marked ? 'currentColor' : 'none'} />
            <span className="sr-only">{marked ? 'Unmark' : 'Mark'} {family.kanji}</span>
          </button>
        )}
      </div>

      <div className="flex-1 min-w-0 text-sm space-y-2">
        {loading && (
          <div className="space-y-2 pt-1">
            <SkeletonLine width="45%" />
            <SkeletonLine width="80%" />
            <SkeletonLine width="95%" />
          </div>
        )}

        {detail && (
          <>
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-medium text-gray-100">{detail.meaning}</span>
              <LevelPill level={detail.jlpt_level} />
            </div>

            <ReadingRow label="on" title="On'yomi — the Chinese-derived reading, mostly used in compounds"
              readings={detail.onyomi} used={detail.reading_kind === 'on' ? detail.reading_in_word : null} />
            <ReadingRow label="kun" title="Kun'yomi — the native Japanese reading, often with okurigana"
              readings={detail.kunyomi} used={detail.reading_kind === 'kun' ? detail.reading_in_word : null} />

            {detail.components.length > 0 && (
              <div className="text-gray-400">
                {detail.components.map((c, i) => (
                  <span key={i}>
                    {i > 0 && <span className="text-gray-600"> + </span>}
                    <span className="jp-text text-gray-200">{c.part}</span>
                    {c.meaning && <span className="text-gray-500"> {c.meaning}</span>}
                  </span>
                ))}
              </div>
            )}

            {detail.origin && (
              <p className="flex gap-1.5 text-gray-400">
                <ScrollText size={14} className="shrink-0 mt-0.5 text-gray-500" />
                <span>{detail.origin}</span>
              </p>
            )}
          </>
        )}

        <ExampleWords kanji={family.kanji} words={detail?.example_words} skip={[word, ...family.words.map(w => w.japanese)]} />

        {family.words.length > 0 && (
          <WordList title={word ? 'Also in your library' : 'In your library'}>
            {family.words.map(w => (
              <WordRow key={w.japanese} word={w.japanese} reading={w.reading} meaning={w.meaning} level={w.jlpt_level} />
            ))}
          </WordList>
        )}
      </div>
    </div>
  )
}

/** Common words built on the kanji, each with a one-line note on how the
 * kanji's meaning shows up in it. The word being drilled and the ones listed
 * from the library are left out so the lists don't repeat each other. */
function ExampleWords({ kanji, words, skip }) {
  const known = new Set(skip)
  const shown = (words || []).filter(w => !known.has(w.word))
  if (!shown.length) return null
  return (
    <WordList title={<>Other words with <span className="jp-text normal-case">{kanji}</span></>}>
      {shown.map(w => (
        <WordRow key={w.word} word={w.word} reading={w.reading} meaning={w.meaning} note={w.link} level={w.jlpt_level} />
      ))}
    </WordList>
  )
}

/** A titled list of WordRows laid out as one grid, so the word column is as
 * wide as the list's longest word or reading (keeping readings on one line)
 * but never more than half the panel, which leaves the English room. */
function WordList({ title, children }) {
  return (
    <div className="pt-2 border-t border-gray-700/60 grid grid-cols-[fit-content(50%)_1fr] gap-x-3 gap-y-1.5">
      <div className="col-span-2 text-[11px] uppercase tracking-wide text-gray-500">{title}</div>
      {children}
    </div>
  )
}

/** Word with its reading beneath on the left, English on the right: two cells
 * of WordList's grid. Stacking the reading gives the meaning the rest of the
 * width, so it rarely wraps on a phone, and when it does it wraps within its
 * own column instead of under the word. */
function WordRow({ word, reading, meaning, note, level }) {
  return (
    <>
      <div className="leading-tight">
        <div className="jp-text text-gray-100">{word}</div>
        {reading && <div className="text-xs text-indigo-300"><span className="jp-text">{reading}</span></div>}
      </div>
      <div className="min-w-0 leading-snug">
        {/* Inline after the text, not a column of its own: a right-hand column
            would take width from the meaning and make it wrap again. */}
        <div className="text-gray-300">
          {meaning}
          {level && <> <LevelPill level={level} small /></>}
        </div>
        {note && <div className="text-xs text-gray-500">{note}</div>}
      </div>
    </>
  )
}

/** JLPT level badge. Unofficial for kanji and vocabulary alike: the JLPT
 * hasn't published lists since 2010, so levels follow common study lists. */
function LevelPill({ level, small = false }) {
  if (!level) return null
  return (
    <span
      title="Unofficial: the JLPT hasn't published kanji or vocabulary lists since 2010, so this follows common study lists"
      className={`shrink-0 text-indigo-300 bg-indigo-500/10 border border-indigo-500/30 rounded-full ${small ? 'text-[10px] px-1 leading-4' : 'text-[11px] px-1.5 py-px'}`}
    >
      {level}
    </span>
  )
}

/** On or kun readings; okurigana (after the ".") is dimmed, and the reading
 * this word uses is highlighted. */
function ReadingRow({ label, title, readings, used }) {
  if (!readings.length) return null
  return (
    <div className="flex items-baseline gap-2">
      <span title={title} className="w-7 shrink-0 text-[11px] uppercase tracking-wide text-gray-500 cursor-help">{label}</span>
      <div className="flex flex-wrap gap-x-1.5 gap-y-1">
        {readings.map(r => {
          const [stem, okurigana] = r.split('.')
          const here = r === used
          return (
            <span key={r}
              className={`jp-text rounded px-1.5 ${here ? 'bg-indigo-500/25 text-indigo-100 ring-1 ring-indigo-400/50' : 'text-gray-300'}`}>
              {stem}{okurigana && <span className={here ? 'text-indigo-300/70' : 'text-gray-500'}>{okurigana}</span>}
            </span>
          )
        })}
      </div>
    </div>
  )
}
