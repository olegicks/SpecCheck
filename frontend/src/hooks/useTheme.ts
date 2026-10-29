import { useCallback, useState } from 'react'

const KEY = 'speccheck-theme'

export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))

  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev
      document.documentElement.classList.toggle('dark', next)
      try {
        localStorage.setItem(KEY, next ? 'dark' : 'light')
      } catch {
        /* storage unavailable (private mode) */
      }
      return next
    })
  }, [])

  return { dark, toggle }
}
