import { createContext, useContext } from 'react'

export const FeaturesContext = createContext({ whisperEnabled: true })
export const useFeatures = () => useContext(FeaturesContext)
