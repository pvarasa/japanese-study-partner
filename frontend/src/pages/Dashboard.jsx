import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Brain, BookOpen, Target, Flame } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
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
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getDashboard().then(setStats).catch(console.error).finally(() => setLoading(false))
  }, [])

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
