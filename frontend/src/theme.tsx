import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'system' | 'morning' | 'rose' | 'lavender' | 'mist' | 'mint' | 'cream'

export const FONT_FAMILY_VALUES: Record<string, string> = {
  system: 'system-ui, -apple-system, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  'microsoft-yahei': '"Microsoft YaHei", "微软雅黑", sans-serif',
  pingfang: '"PingFang SC", "苹方", "Microsoft YaHei", sans-serif',
  'source-han-sans': '"Source Han Sans SC", "Noto Sans SC", sans-serif',
  'noto-sans-sc': '"Noto Sans SC", "Microsoft YaHei", sans-serif',
  'source-han-serif': '"Source Han Serif SC", "Noto Serif SC", serif',
  simsun: 'SimSun, "宋体", serif',
  kaiti: 'KaiTi, "楷体", serif',
  'segoe-ui': '"Segoe UI", "Microsoft YaHei", sans-serif',
  arial: 'Arial, "Helvetica Neue", "Microsoft YaHei", sans-serif',
  roboto: 'Roboto, Arial, "Microsoft YaHei", sans-serif',
  monospace: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace',
}
export const FONT_SCALE_VALUES: Record<string, string> = {
  xsmall: '0.88', small: '0.94', medium: '1', large: '1.06', xlarge: '1.14',
  'size-10': '0.714', 'size-11': '0.786', 'size-12': '0.857', 'size-13': '0.929',
  'size-14': '1', 'size-15': '1.071', 'size-16': '1.143', 'size-18': '1.286',
  'size-20': '1.429', 'size-22': '1.571', 'size-24': '1.714',
}
export function applyStyleSettings(settings: { default_font_family?: string; default_font_size?: string }) {
  const family = FONT_FAMILY_VALUES[settings.default_font_family || 'system'] || FONT_FAMILY_VALUES.system
  const scale = FONT_SCALE_VALUES[settings.default_font_size || 'medium'] || FONT_SCALE_VALUES.medium
  document.documentElement.style.setProperty('--vx-font-family', family)
  document.documentElement.style.setProperty('--vx-font-scale', scale)
  document.documentElement.style.setProperty('--vx-font-size-base', `${14 * Number(scale)}px`)
  document.body.style.fontFamily = family
  document.body.style.fontSize = `calc(14px * ${scale})`
}

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
  const chooseTheme = (next: ThemeMode) => { localStorage.setItem('vx_theme_explicit', 'true'); setTheme(next) }
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () => {
      // Keep the removed night theme internal for system dark preference; it is
      // never exposed as a user-selectable theme.
      document.documentElement.dataset.theme = theme === 'system' ? (media?.matches ? 'dark' : 'morning') : theme
    }
    apply()
    media?.addEventListener('change', apply)
    localStorage.setItem('vx_theme', theme)
    return () => media?.removeEventListener('change', apply)
  }, [theme])
  const value = useMemo(() => ({
    theme,
    setTheme: chooseTheme,
    toggleTheme: () => chooseTheme((['morning', 'rose', 'lavender', 'mist', 'mint', 'cream'] as ThemeMode[])[Math.max(0, ['morning', 'rose', 'lavender', 'mist', 'mint', 'cream'].indexOf(theme) + 1) % 6]),
  }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('ThemeContext is missing')
  return value
}
