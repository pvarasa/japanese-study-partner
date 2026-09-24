import { AlertCircle, CheckCircle, Lightbulb, ScrollText, X } from 'lucide-react'
import { SkeletonLine } from '../../components/Skeleton'
import SpeakButton from '../../components/SpeakButton'
import RatingButtons from './RatingButtons'
import { isReadingAccepted } from './studyLogic'
import { useKanjiDetails } from './useKanjiDetails'

/**
 * Kanji → reading drill. The word is rendered as plain text, deliberately not
 * through <Ruby>: the other study modes always show furigana, which is how a
 * word can mature there without its kanji ever being read unaided.
 *
 * Typing the reading is optional (self-grading still works), but committing
 * to an answer before the reveal is what keeps "I'd have got that" honest.
 */
export default function KanjiReadingCard({
  item, nextItem, progress, revealed, setRevealed, typed, setTyped, error, submitting, onRate, exitStudy,
}) {
  const card = item.reading_card
  const attempted = typed.trim() !== ''
  const correct = attempted && isReadingAccepted(typed, item.reading)
  // Fetched from the moment the card appears, so it's usually ready by the reveal.
  const kanji = useKanjiDetails(item.id, nextItem?.id)

  const onKeyDown = (e) => {
    // Enter also commits IME composition; only reveal on a plain Enter.
    if (e.key !== 'Enter' || e.nativeEvent.isComposing || e.keyCode === 229) return
    e.preventDefault()
    setRevealed(true)
  }

  return (
    <div className="max-w-lg mx-auto space-y-4">
      <div className="flex justify-between items-center text-sm text-gray-500">
        <span>
          {progress}
          <span className="ml-2 text-xs text-gray-600">
            {card ? `${card.srs_reviews} reviews · ${card.srs_lapses} missed` : 'New'}
          </span>
        </span>
        <button onClick={exitStudy} className="text-gray-500 hover:text-gray-300">Exit</button>
      </div>

      <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 text-center min-h-[250px] flex flex-col justify-center">
        {/* Sizes sit on wrappers: .jp-text sizes itself relative to its parent
            (so the app's font-size control scales it), overriding a size class
            on the same element. */}
        <div className="text-5xl font-medium text-gray-100"><span className="jp-text">{item.japanese}</span></div>

        {!revealed ? (
          <div className="mt-8 space-y-3">
            <input
              value={typed}
              onChange={e => setTyped(e.target.value)}
              onKeyDown={onKeyDown}
              lang="ja"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="Type the reading (optional)"
              className="jp-text w-full max-w-xs mx-auto block bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-center text-lg text-gray-100 placeholder:text-gray-600 placeholder:text-sm focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={() => setRevealed(true)}
              className="bg-indigo-600 text-white px-5 py-2 rounded-lg font-medium hover:bg-indigo-500"
            >
              Show reading
            </button>
          </div>
        ) : (
          <div className="mt-4 pt-4 border-t border-gray-800">
            <div className="flex items-center justify-center gap-1">
              <span className="text-2xl text-indigo-300"><span className="jp-text">{item.reading}</span></span>
              <SpeakButton text={item.japanese} size={16} />
            </div>
            {attempted && (
              <div className={`mt-2 flex items-center justify-center gap-1.5 text-sm ${correct ? 'text-green-400' : 'text-red-400'}`}>
                {correct
                  ? <><CheckCircle size={15} /> Correct</>
                  : <><X size={15} /> You typed <span className="jp-text">{typed.trim()}</span></>}
              </div>
            )}
            <div className="text-lg font-medium mt-3">{item.meaning}</div>
            <KanjiBreakdown families={item.kanji || []} {...kanji} />
          </div>
        )}
      </div>

      {revealed && <RatingButtons error={error} submitting={submitting} onRate={onRate} />}
    </div>
  )
}

/**
 * One panel per kanji of the word: meaning, level, on/kun readings with the one
 * this word uses highlighted, the parts it's built from, a mnemonic, where the
 * character comes from, and the other library words that share it — the same
 * kanji read differently (決断 / 断る) is where readings click.
 */
function KanjiBreakdown({ families, details, error, retry }) {
  if (!families.length) return null
  return (
    <div className="mt-5 text-left space-y-2">
      <div className="text-xs uppercase tracking-wide text-gray-500">
        Kanji <span className="normal-case tracking-normal text-gray-600">· highlighted reading is the one used here</span>
      </div>
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} className="shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={retry} className="text-red-200 underline underline-offset-2 hover:text-white">Retry</button>
        </div>
      )}
      {families.map(f => (
        <KanjiPanel key={f.kanji} family={f} detail={details?.[f.kanji]} loading={!details && !error} />
      ))}
    </div>
  )
}

function KanjiPanel({ family, detail, loading }) {
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
              {detail.jlpt_level && (
                <span
                  title="Unofficial: the JLPT hasn't published kanji lists since 2010, so this follows common study lists"
                  className="shrink-0 text-[11px] text-indigo-300 bg-indigo-500/10 border border-indigo-500/30 rounded-full px-1.5 py-px"
                >
                  {detail.jlpt_level}
                </span>
              )}
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

            {detail.mnemonic && (
              <p className="flex gap-1.5 text-amber-100/90">
                <Lightbulb size={14} className="shrink-0 mt-0.5 text-amber-400" />
                <span>{detail.mnemonic}</span>
              </p>
            )}
            {detail.origin && (
              <p className="flex gap-1.5 text-gray-400">
                <ScrollText size={14} className="shrink-0 mt-0.5 text-gray-500" />
                <span>{detail.origin}</span>
              </p>
            )}
          </>
        )}

        {family.words.length > 0 && (
          <div className="pt-2 border-t border-gray-700/60 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-gray-500">Also in your library</div>
            {family.words.map(w => (
              <div key={w.japanese} className="truncate">
                <span className="jp-text text-gray-100">{w.japanese}</span>
                <span className="jp-text text-indigo-300 ml-2">{w.reading}</span>
                <span className="text-gray-500 ml-2">{w.meaning}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
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
