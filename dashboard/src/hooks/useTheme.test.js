import { applyTheme, getTheme, initializeTheme } from './useTheme'
beforeEach(() => { localStorage.clear(); delete document.documentElement.dataset.theme })
test('theme choices persist and survive initialization', () => {
  applyTheme('aiden-blue')
  expect(document.documentElement.dataset.theme).toBe('aiden-blue')
  expect(getTheme()).toBe('aiden-blue')
  initializeTheme()
  expect(document.documentElement.dataset.theme).toBe('aiden-blue')
  applyTheme('midnight')
  expect(localStorage.getItem('aiden-theme')).toBe('midnight')
})
test('unsupported saved values fall back to the studio palette', () => {
  localStorage.setItem('aiden-theme', 'invalid')
  initializeTheme()
  expect(document.documentElement.dataset.theme).toBe('studio')
  applyTheme('invalid')
  expect(document.documentElement.dataset.theme).toBe('studio')
})
