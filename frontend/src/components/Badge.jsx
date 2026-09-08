// Small colored pill used across Items/Ingest/Dashboard for type, level,
// status and tag labels — one place for the "alpha-transparency badge"
// convention documented in CLAUDE.md instead of hand-copying the classes.
const COLORS = {
  gray: 'bg-gray-800 text-gray-500',
  indigo: 'bg-indigo-500/15 text-indigo-400',
  amber: 'bg-amber-500/15 text-amber-400',
  red: 'bg-red-500/15 text-red-400',
  green: 'bg-green-500/15 text-green-400',
}

export default function Badge({ color = 'gray', className = '', children }) {
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${COLORS[color]} ${className}`}>
      {children}
    </span>
  )
}
