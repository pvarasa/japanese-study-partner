import { createContext, useContext } from 'react'

export const JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

// Read-only: App.jsx is the only place the level changes (its two <select>s
// call its own local setter directly), so nothing needs a setter through here.
export const LevelContext = createContext({ jlptLevel: 'N3' })

export const useLevel = () => useContext(LevelContext)
