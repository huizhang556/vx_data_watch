import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'system' | 'morning' | 'rose' | 'lavender' | 'mist' | 'mint' | 'cream'

export const THEME_LABELS: Record<ThemeMode, string> = { system: '跟随系统', morning: '晨曦模式', rose: '玫瑰柔和模式', lavender: '薰衣草模式', mist: '雾蓝模式', mint: '薄荷模式', cream: '奶油模式' }
interface ThemeContextValue { theme: ThemeMode; setTheme: (theme: ThemeMode) => void; toggleTheme: () => void }
const ThemeContext = createContext<ThemeContextValue | null>(null)

function initialTheme(): ThemeMode {
  const stored = localStorage.getItem('vx_theme')
  if (stored === 'light') return 'morning'
  if (stored === 'dark' || stored === 'night') return 'morning'
  if (stored && stored in THEME_LABELS) return stored as ThemeMode
  return 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(initialTheme)
  useEffect(() => {
    const apply = () => { document.documentElement.dataset.theme = theme === 'system' ? 'morning' : theme }
    apply()
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    media?.addEventListener('change', apply)
    localStorage.setItem('vx_theme', theme)
    return () => media?.removeEventListener('change', apply)
  }, [theme])
  const value = useMemo(() => ({
    theme,
    setTheme,
    toggleTheme: () => setTheme((current) => { const modes: ThemeMode[] = ['morning', 'rose', 'lavender', 'mist', 'mint', 'cream']; const index = modes.indexOf(current); return modes[(index + 1) % modes.length] }),
  }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('ThemeContext is missing')
  return value
}
