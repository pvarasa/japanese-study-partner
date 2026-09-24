import { RotateCcw, ArrowRight, Zap, AlertCircle } from 'lucide-react'

/** The self-graded Again / Hard / Good row, with any save error above it. */
export default function RatingButtons({ error, submitting, onRate }) {
  return (
    <div className="space-y-2">
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={15} /> {error}
        </div>
      )}
      <div className="grid grid-cols-3 gap-2">
        <button onClick={() => onRate('again')} disabled={submitting}
          className="bg-red-500/15 text-red-400 border border-red-500/30 py-3 rounded-xl font-medium hover:bg-red-500/25 transition-colors disabled:opacity-50">
          <RotateCcw className="inline mr-1" size={16} /> Again
        </button>
        <button onClick={() => onRate('hard')} disabled={submitting}
          className="bg-orange-500/15 text-orange-400 border border-orange-500/30 py-3 rounded-xl font-medium hover:bg-orange-500/25 transition-colors disabled:opacity-50">
          <Zap className="inline mr-1" size={16} /> Hard
        </button>
        <button onClick={() => onRate('good')} disabled={submitting}
          className="bg-green-500/15 text-green-400 border border-green-500/30 py-3 rounded-xl font-medium hover:bg-green-500/25 transition-colors disabled:opacity-50">
          <ArrowRight className="inline mr-1" size={16} /> Good
        </button>
      </div>
    </div>
  )
}
