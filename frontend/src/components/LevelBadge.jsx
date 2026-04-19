import { useLevel } from '../context/LevelContext'

export default function LevelBadge({ className = '' }) {
  const { jlptLevel } = useLevel()
  return (
    <span
      title="Difficulty follows your JLPT level setting"
      className={`inline-flex items-center gap-1 text-xs text-indigo-300 bg-indigo-500/10 border border-indigo-500/30 rounded-full px-2 py-0.5 ${className}`}
    >
      <span className="text-gray-500">Level</span>
      <span className="font-medium">{jlptLevel}</span>
    </span>
  )
}
