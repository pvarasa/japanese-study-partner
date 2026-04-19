import { useState, useEffect } from 'react'
import { Search, Trash2, Edit3, ChevronDown } from 'lucide-react'
import { api } from '../api'
import Ruby from '../components/Ruby'
import { SkeletonLine } from '../components/Skeleton'

const TYPES = ['all', 'word', 'grammar', 'expression']

export default function Items() {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})

  const load = () => {
    const params = {}
    if (typeFilter !== 'all') params.type = typeFilter
    if (search) params.search = search
    setLoading(true)
    api.getItems(params).then(setItems).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [typeFilter])

  const handleSearch = (e) => {
    e.preventDefault()
    load()
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this item?')) return
    await api.deleteItem(id)
    setItems(items.filter(i => i.id !== id))
  }

  const startEdit = (item) => {
    setEditingId(item.id)
    setEditForm({ japanese: item.japanese, reading: item.reading || '', meaning: item.meaning, notes: item.notes || '' })
  }

  const saveEdit = async (id) => {
    await api.updateItem(id, editForm)
    setEditingId(null)
    load()
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Library</h1>

      {/* Search & filter */}
      <div className="flex gap-2">
        <form onSubmit={handleSearch} className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
          <input
            type="text"
            placeholder="Search words, grammar, expressions..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
          />
        </form>
        <div className="relative">
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="appearance-none bg-gray-900 border border-gray-700 text-gray-100 rounded-lg px-3 py-2 pr-8 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
          >
            {TYPES.map(t => <option key={t} value={t}>{t === 'all' ? 'All types' : t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" size={14} />
        </div>
      </div>

      {/* Items list */}
      {loading ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="px-4 py-3 space-y-2">
              <SkeletonLine width="35%" className="h-4" />
              <SkeletonLine width="55%" />
              <SkeletonLine width="25%" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-8 text-gray-500">No items found</div>
      ) : (
        <div className="bg-gray-900 rounded-xl border border-gray-800 divide-y divide-gray-800">
          {items.map((item) => (
            <div key={item.id} className="px-4 py-3">
              {editingId === item.id ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <input value={editForm.japanese} onChange={e => setEditForm({...editForm, japanese: e.target.value})}
                      className="bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-sm jp-text" placeholder="Japanese" />
                    <input value={editForm.reading} onChange={e => setEditForm({...editForm, reading: e.target.value})}
                      className="bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-sm" placeholder="Reading" />
                  </div>
                  <input value={editForm.meaning} onChange={e => setEditForm({...editForm, meaning: e.target.value})}
                    className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-sm" placeholder="Meaning" />
                  <input value={editForm.notes} onChange={e => setEditForm({...editForm, notes: e.target.value})}
                    className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded px-2 py-1 text-sm" placeholder="Notes" />
                  <div className="flex gap-2">
                    <button onClick={() => saveEdit(item.id)} className="text-sm bg-indigo-600 text-white px-3 py-1 rounded hover:bg-indigo-500">Save</button>
                    <button onClick={() => setEditingId(null)} className="text-sm text-gray-400 px-3 py-1 hover:text-gray-200">Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="flex justify-between items-start">
                  <div>
                    <Ruby text={item.japanese} className="font-medium text-lg" />
                    <div className="text-sm text-gray-400">{item.meaning}</div>
                    {item.notes && <div className="text-xs text-gray-500 mt-0.5">{item.notes}</div>}
                    <div className="flex gap-1 mt-1">
                      <span className="text-xs px-1.5 py-0.5 bg-gray-800 rounded text-gray-500">{item.type}</span>
                      {item.jlpt_level && <span className="text-xs px-1.5 py-0.5 bg-indigo-500/15 rounded text-indigo-400">{item.jlpt_level}</span>}
                      {item.tags?.map(t => <span key={t} className="text-xs px-1.5 py-0.5 bg-green-500/15 rounded text-green-400">{t}</span>)}
                    </div>
                  </div>
                  <div className="flex gap-1 ml-4 shrink-0">
                    <button onClick={() => startEdit(item)} className="p-1.5 text-gray-500 hover:text-indigo-400 rounded"><Edit3 size={14} /></button>
                    <button onClick={() => handleDelete(item.id)} className="p-1.5 text-gray-500 hover:text-red-400 rounded"><Trash2 size={14} /></button>
                  </div>
                </div>
              )}
              {/* SRS info */}
              <div className="flex gap-3 mt-1 text-xs text-gray-600">
                <span>Reviews: {item.srs_reviews}</span>
                {item.srs_reviews > 0 && <span>Accuracy: {Math.round(item.srs_correct / item.srs_reviews * 100)}%</span>}
                <span>Interval: {item.srs_interval < 1 ? `${Math.round(item.srs_interval * 24 * 60)}m` : `${Math.round(item.srs_interval)}d`}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
