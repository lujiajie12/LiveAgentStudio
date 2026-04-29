const THEME_STORAGE_KEY = 'liveagent.theme'
const THEMES = new Set(['dark', 'light'])

export function getPreferredTheme() {
  if (typeof window === 'undefined') {
    return 'dark'
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (THEMES.has(stored)) {
    return stored
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function getCurrentTheme() {
  if (typeof document === 'undefined') {
    return 'dark'
  }
  const current = document.documentElement.dataset.theme
  return THEMES.has(current) ? current : getPreferredTheme()
}

export function applyTheme(theme) {
  const nextTheme = THEMES.has(theme) ? theme : 'dark'
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = nextTheme
    document.documentElement.style.colorScheme = nextTheme
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme)
  }
  return nextTheme
}

export function initTheme() {
  return applyTheme(getPreferredTheme())
}

export function getOppositeTheme(theme = getCurrentTheme()) {
  return theme === 'light' ? 'dark' : 'light'
}
