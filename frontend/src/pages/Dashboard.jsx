import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Brain, BookOpen, Target, Flame, AlertTriangle, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { pct } from '../format'
import Ruby from '../components/Ruby'
import RetentionChart from '../components/RetentionChart'
import { Skeleton, SkeletonLine } from '../components/Skeleton'

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-40" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-gray-900 rounded-xl p-4 border border-gray-800 space-y-2">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <Skeleton className="h-7 w-16" />
            <SkeletonLine width="70%" />
          </div>
        ))}
      </div>
      <div className="space-y-3">
        <Skeleton className="h-5 w-32" />
        <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="px-4 py-3 flex justify-between items-center">
              <SkeletonLine width="40%" />
              <SkeletonLine width="30%" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [restoring, setRestoring] = useState(null)

  useEffect(() => {
    api.getDashboard().then(setStats).catch(console.error).finally(() => setLoading(false))
    // The trend is supplementary — a failure here shouldn't blank the page.
    api.getHistory(60).then(setHistory).catch(console.error)
  }, [])

  // Unsuspending resets the card's history, so refresh the whole dashboard
  // rather than trying to patch the counts locally.
  const restore = async (id) => {
    setRestoring(id)
    try {
      await api.unsuspendItem(id)
      setStats(await api.getDashboard())
    } catch (err) {
      console.error(err)
    }
    setRestoring(null)
  }

  if (loading) return <DashboardSkeleton />
  if (!stats) return <div className="text-center py-12 text-gray-500">Could not load dashboard</div>

  const statCards = [
    { label: 'Total Items', value: stats.total_items, icon: BookOpen, color: 'text-blue-400 bg-blue-500/15' },
    { label: 'Due Today', value: stats.due_today, icon: Target, color: 'text-orange-400 bg-orange-500/15' },
    { label: 'Studied Today', value: stats.studied_today, icon: Brain, color: 'text-green-400 bg-green-500/15' },
    { label: 'Streak', value: `${stats.streak_days}d`, icon: Flame, color: 'text-red-400 bg-red-500/15' },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className={`inline-flex p-2 rounded-lg ${color} mb-2`}>
              <Icon size={20} />
            </div>
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-sm text-gray-500">{label}</div>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      {stats.due_today > 0 && (
        <Link
          to="/study"
          className="block bg-indigo-600 text-white rounded-xl p-4 text-center font-medium hover:bg-indigo-500 transition-colors"
        >
          <Brain className="inline mr-2" size={20} />
          Study {stats.due_today} due items
        </Link>
      )}

      {/* Retention trend */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold">Recall accuracy</h2>
          <span className="text-xs text-gray-500">last 60 days · reviews below</span>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <RetentionChart data={history} />
        </div>
      </div>

      {/* Leeches — cards that keep failing and have been pulled from rotation */}
      {stats.leeches?.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <AlertTriangle size={18} className="text-amber-400" />
              Needs rework
            </h2>
            <span className="text-xs text-gray-500">{stats.suspended_count} suspended</span>
          </div>
          <p className="text-sm text-gray-500 mb-2">
            These kept coming back wrong, so they're out of the review queue. Rewrite the
            card — a sentence beats a bare gloss — then restore it.
          </p>
          <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
            {stats.leeches.map((item) => (
              <div key={item.id} className="px-4 py-3 flex justify-between items-center gap-3">
                <div className="min-w-0">
                  <Ruby text={item.japanese} className="font-medium text-lg" />
                  <div className="text-sm text-gray-400 truncate">{item.meaning}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs px-1.5 py-0.5 bg-red-500/15 rounded text-red-400 tabular-nums">
                    {pct(item.pass_rate ?? 0)} · {item.srs_reviews}×
                  </span>
                  <button
                    onClick={() => restore(item.id)}
                    disabled={restoring === item.id}
                    title="Return to the review queue and reset its history"
                    className="flex items-center gap-1 text-xs text-indigo-400 border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 px-2 py-1 rounded-lg transition-colors disabled:opacity-50"
                  >
                    <RotateCcw size={12} /> Restore
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weak items */}
      {stats.weak_items.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Needs Practice</h2>
          <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
            {stats.weak_items.slice(0, 5).map((item) => (
              <div key={item.id} className="px-4 py-3 flex justify-between items-center">
                <div>
                  <Ruby text={item.japanese} className="font-medium text-lg" />
                </div>
                <div className="text-sm text-gray-400">{item.meaning}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent */}
      {stats.recent_items.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Recently Added</h2>
          <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
            {stats.recent_items.slice(0, 5).map((item) => (
              <div key={item.id} className="px-4 py-3 flex justify-between items-center">
                <div>
                  <Ruby text={item.japanese} className="font-medium text-lg" />
                </div>
                <div className="text-right">
                  <div className="text-sm text-gray-400">{item.meaning}</div>
                  <span className="text-xs px-1.5 py-0.5 bg-gray-800 rounded text-gray-500">
                    {item.type}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats.total_items === 0 && (
        <div className="text-center py-12 text-gray-500">
          <p className="mb-4">No items yet. Start by adding some study materials!</p>
          <Link to="/import" className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-500">
            Import content
          </Link>
        </div>
      )}
    </div>
  )
}
