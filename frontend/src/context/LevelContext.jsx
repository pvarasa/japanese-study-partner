import { createContext, useContext } from 'react'

export const JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

export const LevelContext = createContext({
  jlptLevel: 'N3',
  setJlptLevel: () => {},
})

export const useLevel = () => useContext(LevelContext)
