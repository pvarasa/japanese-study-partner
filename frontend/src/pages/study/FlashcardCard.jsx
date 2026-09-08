import { RotateCcw, ArrowRight, Zap, Sparkles, Loader2, AlertCircle } from 'lucide-react'
import Ruby from '../../components/Ruby'
import SpeakButton from '../../components/SpeakButton'

export default function FlashcardCard({
  mode, item, progress, revealed, setRevealed, shownExamples,
  generatedExample, generatingExample, generateExample, error, onRate, exitStudy,
}) {
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
            {shownExamples.map((ex, i) => (
              <div key={i} className="mt-3 text-sm text-left bg-gray-800 rounded-lg p-3">
                <div className="flex items-start justify-between gap-1">
                  <Ruby text={ex.japanese} className="text-gray-200" />
                  <SpeakButton text={ex.japanese} className="shrink-0 -mt-1" size={14} />
                </div>
                <div className="text-gray-500 mt-1">{ex.english}</div>
              </div>
            ))}
            <button
              onClick={async (e) => { e.stopPropagation(); await generateExample() }}
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

      {revealed && (
        <div className="space-y-2">
          {error && (
            <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              <AlertCircle size={15} /> {error}
            </div>
          )}
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => onRate('again')}
              className="bg-red-500/15 text-red-400 border border-red-500/30 py-3 rounded-xl font-medium hover:bg-red-500/25 transition-colors">
              <RotateCcw className="inline mr-1" size={16} /> Again
            </button>
            <button onClick={() => onRate('hard')}
              className="bg-orange-500/15 text-orange-400 border border-orange-500/30 py-3 rounded-xl font-medium hover:bg-orange-500/25 transition-colors">
              <Zap className="inline mr-1" size={16} /> Hard
            </button>
            <button onClick={() => onRate('good')}
              className="bg-green-500/15 text-green-400 border border-green-500/30 py-3 rounded-xl font-medium hover:bg-green-500/25 transition-colors">
              <ArrowRight className="inline mr-1" size={16} /> Good
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
