import { Routes, Route, NavLink } from 'react-router-dom'
import { BookOpen, Brain, BarChart3, Upload, Menu, X, FileText, Minus, Plus, MessagesSquare } from 'lucide-react'
import { useState, useEffect } from 'react'
import Dashboard from './pages/Dashboard'
import Items from './pages/Items'
import Study from './pages/Study'
import Ingest from './pages/Ingest'
import Reading from './pages/Reading'
import Converse from './pages/Converse'
import { api } from './api'
import { LevelContext, JLPT_LEVELS } from './context/LevelContext'

const navItems = [
  { to: '/', icon: BarChart3, label: 'Dashboard' },
  { to: '/items', icon: BookOpen, label: 'Library' },
  { to: '/import', icon: Upload, label: 'Import' },
  { to: '/study', icon: Brain, label: 'Study' },
  { to: '/reading', icon: FileText, label: 'Read' },
  { to: '/converse', icon: MessagesSquare, label: 'Converse' },
]

const JP_SIZES = [
  { jp: 0.85, rt: 0.4, label: 'S' },
  { jp: 1,    rt: 0.5, label: 'M' },
  { jp: 1.2,  rt: 0.55, label: 'L' },
  { jp: 1.4,  rt: 0.6, label: 'XL' },
]

function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [sizeIdx, setSizeIdx] = useState(() => {
    const saved = localStorage.getItem('jp-size')
    return saved !== null ? Number(saved) : 1
  })
  const [jlptLevel, setJlptLevelState] = useState(() => {
    return localStorage.getItem('jlpt-level') || 'N3'
  })

  useEffect(() => {
    const s = JP_SIZES[sizeIdx]
    document.documentElement.style.setProperty('--jp-scale', s.jp)
    document.documentElement.style.setProperty('--rt-scale', s.rt)
    localStorage.setItem('jp-size', sizeIdx)
  }, [sizeIdx])

  useEffect(() => {
    let cancelled = false
    api.getSettings().then((s) => {
      if (cancelled) return
      if (s?.jlpt_level && JLPT_LEVELS.includes(s.jlpt_level)) {
        setJlptLevelState(s.jlpt_level)
        localStorage.setItem('jlpt-level', s.jlpt_level)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const setJlptLevel = (level) => {
    if (!JLPT_LEVELS.includes(level) || level === jlptLevel) return
    setJlptLevelState(level)
    localStorage.setItem('jlpt-level', level)
    api.updateSettings({ jlpt_level: level }).catch(() => {})
  }

  return (
    <LevelContext.Provider value={{ jlptLevel, setJlptLevel }}>
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <NavLink to="/" className="text-xl font-bold text-indigo-400 jp-text">
            日本語 Study Partner
          </NavLink>

          {/* Desktop nav */}
          <nav className="hidden md:flex gap-1">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-500/20 text-indigo-400'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>

          {/* JLPT level selector */}
          <div className="hidden md:flex items-center ml-2">
            <label className="sr-only" htmlFor="jlpt-level-desktop">JLPT level</label>
            <select
              id="jlpt-level-desktop"
              value={jlptLevel}
              onChange={(e) => setJlptLevel(e.target.value)}
              title="JLPT level (adapts AI-generated content)"
              className="bg-gray-800 text-gray-200 text-xs rounded-lg px-2 py-1.5 border border-gray-800 hover:border-gray-700 focus:outline-none focus:border-indigo-500"
            >
              {JLPT_LEVELS.map((lvl) => (
                <option key={lvl} value={lvl}>{lvl}</option>
              ))}
            </select>
          </div>

          {/* Font size control */}
          <div className="hidden md:flex items-center gap-0.5 ml-2 bg-gray-800 rounded-lg px-1 py-0.5">
            <button onClick={() => setSizeIdx(Math.max(0, sizeIdx - 1))} disabled={sizeIdx === 0}
              className="p-1 text-gray-400 hover:text-gray-200 disabled:opacity-30">
              <Minus size={12} />
            </button>
            <span className="text-xs text-gray-500 w-5 text-center jp-text" style={{ fontSize: '11px' }}>字</span>
            <button onClick={() => setSizeIdx(Math.min(JP_SIZES.length - 1, sizeIdx + 1))} disabled={sizeIdx === JP_SIZES.length - 1}
              className="p-1 text-gray-400 hover:text-gray-200 disabled:opacity-30">
              <Plus size={12} />
            </button>
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 text-gray-400"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {/* Mobile nav */}
        {menuOpen && (
          <nav className="md:hidden border-t border-gray-800 bg-gray-900 px-4 pb-3">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                    isActive
                      ? 'bg-indigo-500/20 text-indigo-400'
                      : 'text-gray-400 hover:bg-gray-800'
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400">
              <span>JLPT level</span>
              <select
                value={jlptLevel}
                onChange={(e) => setJlptLevel(e.target.value)}
                className="bg-gray-800 text-gray-200 text-xs rounded-lg px-2 py-1 border border-gray-800"
              >
                {JLPT_LEVELS.map((lvl) => (
                  <option key={lvl} value={lvl}>{lvl}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400">
              <span>Font size</span>
              <div className="flex items-center gap-1 bg-gray-800 rounded-lg px-2 py-1">
                <button onClick={() => setSizeIdx(Math.max(0, sizeIdx - 1))} disabled={sizeIdx === 0}
                  className="p-1 text-gray-400 hover:text-gray-200 disabled:opacity-30"><Minus size={14} /></button>
                <span className="text-xs text-gray-500 w-6 text-center">{JP_SIZES[sizeIdx].label}</span>
                <button onClick={() => setSizeIdx(Math.min(JP_SIZES.length - 1, sizeIdx + 1))} disabled={sizeIdx === JP_SIZES.length - 1}
                  className="p-1 text-gray-400 hover:text-gray-200 disabled:opacity-30"><Plus size={14} /></button>
              </div>
            </div>
          </nav>
        )}
      </header>

      {/* Content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/items" element={<Items />} />
          <Route path="/study" element={<Study />} />
          <Route path="/import" element={<Ingest />} />
          <Route path="/reading" element={<Reading />} />
          <Route path="/converse" element={<Converse />} />
        </Routes>
      </main>
    </div>
    </LevelContext.Provider>
  )
}

export default App
