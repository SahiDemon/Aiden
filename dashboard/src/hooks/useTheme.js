import { useEffect, useState } from 'react'
export const themes = [
  { id: 'studio', name: 'Warm studio', description: 'Charcoal olive & soft amber', colors: ['#171914', '#282e22', '#d3b071'] },
  { id: 'aiden-blue', name: 'Aiden blue', description: 'Deep navy & signature blue', colors: ['#101727', '#202f49', '#85b1ff'] },
  { id: 'midnight', name: 'Midnight blue', description: 'Near-black & cool blue', colors: ['#0c111b', '#1c2535', '#a4bdeb'] },
]
export function getTheme() {
  try { const saved = localStorage.getItem('aiden-theme'); return themes.some(theme => theme.id === saved) ? saved : 'studio' }
  catch { return 'studio' }
}
export function applyTheme(id) {
  if (!themes.some(theme => theme.id === id)) return
  document.documentElement.dataset.theme = id
  try { localStorage.setItem('aiden-theme', id) } catch { /* Still applies for this session. */ }
  window.dispatchEvent(new Event('aiden-theme-change'))
}
export function initializeTheme() { document.documentElement.dataset.theme = getTheme() }
export default function useTheme() {
  const [theme, setTheme] = useState(getTheme)
  useEffect(() => {
    const update = () => { const id = getTheme(); setTheme(id); document.documentElement.dataset.theme = id }
    window.addEventListener('aiden-theme-change', update)
    window.addEventListener('storage', update)
    return () => { window.removeEventListener('aiden-theme-change', update); window.removeEventListener('storage', update) }
  }, [])
  return { theme, setTheme: applyTheme }
}
