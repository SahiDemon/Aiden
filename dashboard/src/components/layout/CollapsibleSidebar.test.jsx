import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import CollapsibleSidebar from './CollapsibleSidebar'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

jest.mock('framer-motion', () => ({
  AnimatePresence: ({ children }) => children,
  motion: {
    div: ({ initial, animate, exit, transition, children, ...props }) => (
      <div {...props}>{children}</div>
    ),
  },
}))
jest.mock('../system/SystemStats', () => () => <div>System metrics panel</div>)
jest.mock('../smart-home/SmartDeviceCard', () => () => <div>Smart devices panel</div>)

test('System Status opens the panel and the named toggle closes it', () => {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  try {
    act(() => root.render(<CollapsibleSidebar connected />))
    expect(container.textContent).not.toContain('System metrics panel')
    act(() => container.querySelector('button[title="System Status"]').click())
    expect(container.textContent).toContain('System metrics panel')
    expect(container.textContent).toContain('Smart devices panel')
    act(() => container.querySelector('button[aria-label="Collapse status panel"]').click())
    expect(container.textContent).not.toContain('System metrics panel')
    expect(container.querySelector('button[aria-label="Expand status panel"]')).not.toBeNull()
  } finally {
    act(() => root.unmount())
    container.remove()
  }
})
